from flask import Blueprint, jsonify, request
from .domain import BalanceRepository, BalanceService


class BalanceBlueprint:
    def __init__(self, service: BalanceService):
        self.service = service
        self.blueprint = Blueprint('balance_api', __name__)
        self._register_routes()

    def _register_routes(self) -> None:
        @self.blueprint.route('/balance', methods=['POST'])
        def get_balance():
            payload = request.get_json(silent=True) or {}
            customer_id = payload.get('customer_id')
            body, status = self.service.get_balance_response(customer_id)
            return jsonify(body), status


def create_balance_blueprint() -> Blueprint:
    repository = BalanceRepository()
    service = BalanceService(repository)
    balance_blueprint = BalanceBlueprint(service)
    return balance_blueprint.blueprint
