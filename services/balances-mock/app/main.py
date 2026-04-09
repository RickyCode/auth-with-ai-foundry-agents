from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


class AppConfig:
    def __init__(self) -> None:
        self.debug = False
        self.testing = False
        self.json_sort_keys = False

    def apply(self, app: Flask) -> None:
        app.debug = self.debug
        app.testing = self.testing
        app.config['JSON_SORT_KEYS'] = self.json_sort_keys


class BalanceMockService:
    def __init__(self) -> None:
        self.app = Flask(__name__)
        self.config = AppConfig()

    def register_middlewares(self) -> None:
        self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_for=1, x_proto=1)

    def register_blueprints(self) -> None:
        from .api import create_balance_blueprint

        balance_blueprint = create_balance_blueprint()
        self.app.register_blueprint(balance_blueprint, url_prefix='/api')

    def configure(self) -> None:
        self.config.apply(self.app)

    def create_app(self) -> Flask:
        self.configure()
        self.register_middlewares()
        self.register_blueprints()
        return self.app


def get_app() -> Flask:
    service = BalanceMockService()
    return service.create_app()


if __name__ == '__main__':
    application = get_app()
    application.run(host='0.0.0.0', port=8000, debug=True)
