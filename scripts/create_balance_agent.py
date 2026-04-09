# import json
import os

import dotenv
import requests

# from azure.ai.projects import AIProjectClient
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import FunctionTool
from azure.identity import DefaultAzureCredential

dotenv.load_dotenv()


BALANCE_AGENT_INSTRUCTIONS = """
Eres el Agente de Balances de un banco.

Tu objetivo es:
- Consultar el saldo actual de la cuenta del cliente.
- Usar exclusivamente la herramienta disponible para obtener el saldo.
- Responder SIEMPRE en español, en lenguaje natural, de forma breve y clara.

Reglas:
- La herramienta `get_current_balance` devuelve un JSON con el campo `balance`.
- Interpreta `balance` como el saldo actual de la cuenta del cliente.
- Si la herramienta no devuelve un saldo válido, responde con un mensaje genérico:
  "En este momento no puedo obtener tu saldo. Inténtalo más tarde."
- No inventes saldos ni montos.
- No menciones el nombre de la herramienta ni detalles técnicos en la respuesta al usuario.

Formato de respuesta:
- Una sola frase en español dirigida al cliente, por ejemplo:
  "Tu saldo actual es de 1234.50 pesos."
"""


# def get_current_balance(customer_id: str) -> str:
def get_current_balance() -> str:
    """
    Obtiene el saldo actual de un cliente llamando al servicio de balances.

    :return: Cadena JSON con el campo "balance" si la consulta es exitosa.
    """
    base_url = os.environ.get('BALANCE_API_BASE_URL', 'http://localhost:8000')
    url = f"{base_url.rstrip('/')}/api/balance"

    response = requests.post(
        url,
        # json={'customer_id': customer_id},
        json={},
        timeout=5,
    )
    response.raise_for_status()
    return response.text


def main() -> None:
    project_endpoint = os.environ['PROJECT_ENDPOINT']
    model_name = os.environ['MODEL_DEPLOYMENT_NAME']

    user_functions = {get_current_balance}
    function_tool = FunctionTool(functions=user_functions)

    credential = DefaultAzureCredential()

    # project_client = AIProjectClient(
    #     endpoint=project_endpoint,
    #     credential=credential,
    # )
    project_client = AgentsClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    with project_client:
        agent = project_client.create_agent(
            model=model_name,
            name='balance-agent',
            instructions=BALANCE_AGENT_INSTRUCTIONS,
            tools=function_tool.definitions,
            temperature=0.4,
            top_p=0.9,
            description='Agente para consultar el saldo actual de la cuenta del cliente.',
        )

    print('Balance agent created.')
    print('Agent ID:', agent.id)


if __name__ == '__main__':
    main()
