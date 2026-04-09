from flask import Blueprint, jsonify, request

from .auth import verify_token
from .domain import BalanceRepository, BalanceService

repo = BalanceRepository()


class BalanceBlueprint:
    def __init__(self, service: BalanceService):
        self.service = service
        self.blueprint = Blueprint('balance_api', __name__)
        self._register_routes()

    def _register_routes(self) -> None:
        @self.blueprint.route('/balance', methods=['POST'])
        def get_balance():
            auth_header = request.headers.get('Authorization')

            if not auth_header:
                return jsonify({'error': 'Missing token'}), 401

            token = auth_header.replace('Bearer ', '')

            try:
                payload = verify_token(token)
            except Exception as e:
                return jsonify({'error': str(e)}), 401

            customer_id = payload.get('customer_id')

            if not customer_id:
                return jsonify({'error': 'customer_id not found in token'}), 400

            balance = repo.get_balance(customer_id)

            return jsonify(
                {
                    'customer_id': customer_id,
                    'balance': balance,
                }
            )

        @self.blueprint.route('/balance', methods=['GET'])
        def test():
            return 'Done!'


def create_balance_blueprint() -> Blueprint:
    repository = BalanceRepository()
    service = BalanceService(repository)
    balance_blueprint = BalanceBlueprint(service)
    return balance_blueprint.blueprint
