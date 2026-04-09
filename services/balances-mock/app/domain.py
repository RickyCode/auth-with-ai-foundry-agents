from http import HTTPStatus


class BalanceRepository:
    def __init__(self):
        self._balances = {
            'customer-001': 152000.50,
            'customer-002': 87500.00,
            'customer-003': 43120.75,
        }

    def get_balance(self, customer_id: str) -> float | None:
        return self._balances.get(customer_id)


class BalanceService:
    def __init__(self, repository: BalanceRepository):
        self._repository = repository

    def get_balance_response(self, customer_id: str) -> tuple[dict, int]:
        if not customer_id:
            return (
                {
                    'message': 'Unable to process your request at this time.',
                },
                HTTPStatus.BAD_REQUEST,
            )

        balance = self._repository.get_balance(customer_id)

        if balance is None:
            return (
                {
                    'message': 'Unable to process your request at this time.',
                },
                HTTPStatus.OK,
            )

        return (
            {
                'balance_actual': balance,
            },
            HTTPStatus.OK,
        )
