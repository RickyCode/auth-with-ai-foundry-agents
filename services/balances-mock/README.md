# Servicio Mock de Balances

Es un microservicio HTTP en Python (Flask) que expone un endpoint `POST /api/balance` para devolver el saldo actual de un cliente.

Recibe dos tokens en los headers:

* Un **JWT de usuario** emitido por Keycloak, desde el cual obtiene el `customer_id`.
* Un **token del agente de IA** (client_credentials) para autenticar la llamada de servicio a servicio.

Con el `customer_id`, consulta una tabla simulada en memoria `customer_id → balance_actual` y responde con un JSON del tipo:

```json
{
  "balance_actual": 152000.50
}
```

Si la autenticación o validación falla, devuelve una respuesta genérica de error en lugar de datos de saldo.


* `app/main.py`: crea la app Flask, registra blueprints, carga config.
* `app/api.py`: define `POST /api/balance`, parsea headers/body y llama a `auth` + `domain`.
* `app/auth.py`:

  * Valida JWT de usuario (Keycloak).
  * Valida token del agente (introspection o validación básica).
* `app/domain.py`:

  * Mapa en memoria `customer_id -> balance_actual`.
  * Función tipo `get_balance(customer_id)`.
* `config/settings.py`: centraliza lectura de env vars (issuer, audience, jwks_url, client_id, etc.).
* `tests/`: pruebas aisladas del endpoint y de la lógica de dominio.

Para ejecutar correctamente:

```cmd
python -m services.balances-mock.app.main
```
desde la ruta raíz del repositorio.