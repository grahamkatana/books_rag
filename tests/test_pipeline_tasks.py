import sys
sys.path.insert(0, ".")

import os
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")

from unittest.mock import patch

from app.worker.celery_app import celery_app
from app.worker import tasks
import app.cli as cli

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

print("--- run_books_pipeline_task calls cmd_pipeline with the right force value ---")
calls = []


def fake_cmd_pipeline(args):
    calls.append(args.force)


with patch.object(cli, "cmd_pipeline", fake_cmd_pipeline):
    result = tasks.run_books_pipeline_task.delay(force=True)
assert result.get() == "done"
assert calls == [True]
print("OK")

print("\n--- run_papers_pipeline_task calls cmd_pipeline_papers, force defaults to False ---")
calls2 = []


def fake_cmd_pipeline_papers(args):
    calls2.append(args.force)


with patch.object(cli, "cmd_pipeline_papers", fake_cmd_pipeline_papers):
    result2 = tasks.run_papers_pipeline_task.delay()
assert result2.get() == "done"
assert calls2 == [False]
print("OK")

print("\n--- a real failure partway through the pipeline propagates as a genuine Celery failure ---")


def failing_pipeline(args):
    raise RuntimeError("stopped at step 3 (chunk)")


with patch.object(cli, "cmd_pipeline", failing_pipeline):
    try:
        tasks.run_books_pipeline_task.delay(force=False)
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "stopped at step 3" in str(e)
print("OK")

print("\nAll pipeline-task assertions passed.")