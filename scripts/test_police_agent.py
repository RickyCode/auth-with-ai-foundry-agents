import json
import os

import dotenv
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import ListSortOrder, MessageRole
from azure.identity import DefaultAzureCredential

dotenv.load_dotenv()

POLICE_AGENT_ID = os.environ['POLICE_AGENT_ID']
PROJECT_ENDPOINT = os.environ['PROJECT_ENDPOINT']

client = AgentsClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)


def call_policia(user_input: str) -> str:
    # 1. Crear thread
    thread = client.threads.create()

    # 2. Crear mensaje de usuario
    client.messages.create(
        thread_id=thread.id,
        role='user',  # o MessageRole.USER
        content=user_input,
    )

    # 3. Ejecutar el run (y esperar que termine)
    client.runs.create_and_process(
        thread_id=thread.id,
        agent_id=POLICE_AGENT_ID,
    )

    # 4. Leer último mensaje del agente policía
    messages = client.messages.list(
        thread_id=thread.id,
        order=ListSortOrder.ASCENDING,
    )

    last_agent_text = None
    for msg in messages:
        if msg.role in [MessageRole.AGENT, 'assistant', 'agent']:
            if msg.text_messages:
                last_agent_text = msg.text_messages[-1].text.value

    return last_agent_text or ''


if __name__ == '__main__':
    # os.environ.setdefault("POLICE_AGENT_ID")

    resultado = call_policia('Quiero ver mi saldo')
    print('Respuesta del agente Policía:')
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
