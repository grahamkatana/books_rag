"""
Admin-only AI usage and cost: what was spent per model and day, a month-end projection, provider balances where a
provider offers them, and the editable price list and manual credit figures the estimates rest on.

Endpoints:
    GET /api/v1/admin/usage/summary?days=30
    GET /api/v1/admin/usage/prices        PUT /api/v1/admin/usage/prices
    PUT /api/v1/admin/usage/credits
    GET /api/v1/admin/usage/balances
"""

from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import Schema, fields, validate

from app import usage
from app.auth.decorators import admin_required
from app.db.session import get_session
from app.usage import balances

blp = Blueprint("admin_usage", __name__, url_prefix="/api/v1/admin/usage", description="Admin-only AI usage, cost and balances")


class PriceSchema(Schema):
    provider = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    model = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    input_per_million = fields.Float(required=True, validate=validate.Range(min=0, max=100000))
    output_per_million = fields.Float(required=True, validate=validate.Range(min=0, max=100000))
    note = fields.Str(load_default="", validate=validate.Length(max=200))


class CreditSchema(Schema):
    provider = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    amount_usd = fields.Float(required=True, validate=validate.Range(min=0, max=10_000_000))


@blp.route("/summary")
class Summary(MethodView):
    @admin_required
    @blp.arguments(Schema.from_dict({"days": fields.Int(load_default=30, validate=validate.Range(min=1, max=365))})(), location="query")
    def get(self, args):
        with get_session() as session:
            return usage.summary(session, args["days"])


@blp.route("/prices")
class Prices(MethodView):
    @admin_required
    def get(self):
        with get_session() as session:
            return {"prices": usage.list_prices(session)}

    @admin_required
    @blp.arguments(PriceSchema)
    def put(self, body):
        with get_session() as session:
            usage.set_price(session, body["provider"], body["model"], body["input_per_million"], body["output_per_million"], body["note"])
        return {"ok": True}


@blp.route("/credits")
class Credits(MethodView):
    @admin_required
    @blp.arguments(CreditSchema)
    def put(self, body):
        with get_session() as session:
            usage.set_credit(session, body["provider"], body["amount_usd"])
        return {"ok": True}


@blp.route("/balances")
class Balances(MethodView):
    @admin_required
    def get(self):
        with get_session() as session:
            return {"checked": balances.check_all(), "estimated_from_top_up": usage.estimated_credit_left(session)}
