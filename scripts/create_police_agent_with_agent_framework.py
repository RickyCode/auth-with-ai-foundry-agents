import asyncio
import os

import dotenv
from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient

# from azure.identity.aio import AzureCliCredential
from azure.identity import DefaultAzureCredential

dotenv.load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, 'agents', 'prompts', 'policia.md')


async def create_policia_agent() -> ChatAgent:
    """Devuelve una instancia de ChatAgent (Agente Policía) lista para usar."""
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        instructions = f.read()

    project_endpoint = os.environ['PROJECT_ENDPOINT']
    model_deployment_name = os.environ['MODEL_DEPLOYMENT_NAME']

    # credential = AzureCliCredential()
    credential = DefaultAzureCredential()

    chat_client = AzureAIAgentClient(
        async_credential=credential,
        project_endpoint=project_endpoint,
        model_deployment_name=model_deployment_name,
    )

    agent = ChatAgent(
        chat_client=chat_client,
        name='agente-policia-saldo-agent-framework',
        instructions=instructions,
    )

    return agent


async def main():
    agent = await create_policia_agent()

    # result = await agent.run("Quiero ver mi saldo")
    result = await agent.run('Holaaaaaaa')

    print(result.text)


if __name__ == '__main__':
    asyncio.run(main())
