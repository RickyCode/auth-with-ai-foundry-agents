'''
Creates a police agent using Azure AI AgentsClient.
'''

import os

import dotenv
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential

dotenv.load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, 'agents', 'prompts', 'policia.md')


def main():
    '''
    Creates a police agent using Azure AI AgentsClient.
    '''
    endpoint = os.environ['PROJECT_ENDPOINT']
    model_name = os.environ['MODEL_DEPLOYMENT_NAME']

    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        instructions = f.read()

    credential = DefaultAzureCredential()

    with AgentsClient(endpoint=endpoint, credential=credential) as client:
        agent = client.create_agent(
            model=model_name,
            name='agente-policia-saldo',
            instructions=instructions,
            # response_format={"type": "json_object"},
        )

    print('Agente Policía creado.')
    print('ID del agente:', agent.id)


if __name__ == '__main__':
    main()
