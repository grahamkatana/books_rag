"""Usage counting and costing. Runs on an in-memory SQLite database, never the real one."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import usage
from app.models.base import Base
import app.models  # noqa: F401  (registers every table)
from app.models.usage import UsageEvent
from app.usage import balances


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    f = sessionmaker(bind=engine)
    with patch.object(usage, "SessionLocal", f):
        yield f


def test_cost_per_million_tokens():
    assert usage.cost_usd(1_000_000, 0, (0.13, 0)) == pytest.approx(0.13)
    assert usage.cost_usd(500_000, 2_000_000, (1, 3)) == pytest.approx(6.5)
    assert usage.cost_usd(10, 10, None) is None


def test_projection_carries_the_average_to_month_end():
    assert usage.project_month(10.0, datetime(2026, 10, 11)) == pytest.approx(31.0)
    assert usage.project_month(0.0, datetime(2026, 10, 1)) == 0.0


def test_record_and_summary(factory):
    usage.record("embed", "openai", "text-embedding-3-large", 1_000_000)
    usage.record("chat", "openai", "gpt-5.4-mini", 2000, 500)
    with factory() as s:
        usage.set_price(s, "openai", "text-embedding-3-large", 0.13, 0)
        out = usage.summary(s, 30)
    by = {m["model"]: m for m in out["by_model"]}
    assert by["text-embedding-3-large"]["cost_usd"] == pytest.approx(0.13)
    assert by["gpt-5.4-mini"]["priced"] is False and "openai/gpt-5.4-mini" in out["unpriced"]
    assert out["month_to_date_usd"] == pytest.approx(0.13)


def test_credit_estimate_subtracts_spend_since_entry(factory):
    with factory() as s:
        usage.set_price(s, "openai", "m", 10, 0)
        usage.set_credit(s, "openai", 5)
    usage.record("chat", "openai", "m", 100_000)  # $1.00 after the credit was entered
    with factory() as s:
        left = usage.estimated_credit_left(s)[0]
    assert left["estimated_left_usd"] == pytest.approx(4.0)


def test_record_never_raises_when_the_database_is_down():
    with patch.object(usage, "SessionLocal", side_effect=RuntimeError("down")):
        usage.record("chat", "openai", "m", 1, 1)


def test_agent_usage_is_recorded_only_when_real_counts(factory):
    usage.record_agent("verify", "openai", "m", SimpleNamespace(usage=lambda: SimpleNamespace(input_tokens=7, output_tokens=3)))
    usage.record_agent("verify", "openai", "m", MagicMock())  # a test double must not write a row
    with factory() as s:
        rows = s.scalars(select(UsageEvent)).all()
    assert [(r.input_tokens, r.output_tokens) for r in rows] == [(7, 3)]


def test_streaming_answer_records_the_final_usage_chunk(factory):
    from app.retrieval.query_engine import ask_llm_stream
    text = SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi"))])
    last = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=40, completion_tokens=5), choices=[])
    client = MagicMock(); client.chat.completions.create.return_value = iter([text, last])
    assert "".join(ask_llm_stream(client, "q", "c", "gpt-5.4-mini", "")) == "Hi"
    assert client.chat.completions.create.call_args.kwargs["stream_options"] == {"include_usage": True}
    with factory() as s:
        assert [(r.kind, r.input_tokens, r.output_tokens) for r in s.scalars(select(UsageEvent))] == [("chat", 40, 5)]


def test_deepseek_balance_reads_the_documented_shape():
    reply = MagicMock(); reply.json.return_value = {"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "4.20"}]}
    with patch("app.usage.balances.requests.get", return_value=reply) as get:
        out = balances.deepseek_balance("k")
    assert out["balances"][0]["total_balance"] == "4.20"
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer k"


def test_openai_month_spend_adds_every_bucket():
    reply = MagicMock(); reply.json.return_value = {"data": [{"results": [{"amount": {"value": 1.5}}, {"amount": {"value": 0.25}}]}, {"results": [{"amount": {"value": 2}}]}]}
    with patch("app.usage.balances.requests.get", return_value=reply):
        assert balances.openai_month_spend("k")["month_to_date_usd"] == pytest.approx(3.75)


def test_one_failing_provider_does_not_hide_the_rest():
    with patch.object(balances, "DEEPSEEK_API_KEY", "x"), patch.object(balances, "OPENAI_ADMIN_KEY", None), \
         patch.object(balances, "deepseek_balance", side_effect=RuntimeError("boom")):
        out = balances.check_all()
    assert out[0]["kind"] == "error" and any(o["provider"] == "gemini" for o in out)


def test_a_response_without_usage_is_estimated_not_a_crash(factory):
    """Test doubles and some providers return no usage object; the answer must still work."""
    class NoUsage: data = []
    usage.record_embedding("text-embedding-3-large", NoUsage(), ["abcdefgh"])
    with factory() as s:
        row = s.scalars(select(UsageEvent)).one()
    assert (row.input_tokens, row.estimated) == (2, True)
