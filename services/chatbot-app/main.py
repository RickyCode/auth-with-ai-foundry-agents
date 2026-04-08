import os
import time
from pathlib import Path

import dotenv
import requests
from azure.ai.agents import AgentsClient

# from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from logging_agent_event_handler import LoggingAgentEventHandler
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from utils import append_jsonl, safe_serialize, utc_now_iso

dotenv.load_dotenv()

KEYCLOAK_BASE_URL = os.getenv('KEYCLOACK_BASE_URL')
REALM_NAME = os.getenv('REALM_NAME')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

REDIRECT_URI = 'http://localhost:5000/callback'

AUTH_URL = f'{KEYCLOAK_BASE_URL}/realms/{REALM_NAME}/protocol/openid-connect/auth'
TOKEN_URL = f'{KEYCLOAK_BASE_URL}/realms/{REALM_NAME}/protocol/openid-connect/token'

PROJECT_ENDPOINT = os.getenv('PROJECT_ENDPOINT')
BALANCE_AGENT_ID = os.getenv('BALANCE_AGENT_ID')

BALANCE_API_BASE_URL = os.getenv('BALANCE_API_BASE_URL')

LOG_DIR = Path('logs/agents')
LOG_DIR.mkdir(parents=True, exist_ok=True)

balance_api_url = f'{BALANCE_API_BASE_URL}/api/balance'

client = AgentsClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())

app = FastAPI(title='POC Balance Chat')

app.add_middleware(
    SessionMiddleware,
    secret_key='cambiar-por-una-secret-key-segura',
)


@app.get('/')
async def home(request: Request):
    token = request.session.get('access_token')
    return {'logged_in': bool(token)}


@app.get('/login')
async def login():
    url = (
        f'{AUTH_URL}' f'?client_id={CLIENT_ID}' f'&response_type=code' f'&redirect_uri={REDIRECT_URI}' f'&scope=openid'
    )
    return RedirectResponse(url)


@app.get('/callback')
async def callback(request: Request, code: str):
    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post(TOKEN_URL, data=data, headers=headers)

    if response.status_code != 200:
        return JSONResponse(
            {'error': 'token exchange failed', 'details': response.text},
            status_code=400,
        )

    tokens = response.json()

    request.session['access_token'] = tokens['access_token']

    return RedirectResponse(url='/')


@app.get('/logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/', status_code=302)


class Message(BaseModel):
    message: str


#     user_message = body.get("message")
# @app.post("/chat")
# async def chat(message: Message, request: Request):
#     user_message = message.message

#     if not user_message:
#         return JSONResponse({"error": "message is required"}, status_code=400)

#     access_token = request.session.get("access_token")
#     if not access_token:
#         return JSONResponse({"error": "user is not authenticated"}, status_code=401)

#     thread = client.threads.create()
#     print(f"Created thread with ID: {thread.id}")

#     client.messages.create(
#         thread_id=thread.id,
#         role="user",
#         content=user_message,
#     )

#     run = client.runs.create(
#         thread_id=thread.id,
#         agent_id=BALANCE_AGENT_ID,
#     )
#     print(f"Created run with ID: {run.id} and initial status: {run.status}")

#     while run.status in ["queued", "in_progress", "requires_action"]:
#         print(f"Run status: {run.status}")
#         if run.status == "requires_action":
#             tool_outputs = []

#             required_action = run.required_action
#             submit_tool_outputs = required_action.submit_tool_outputs

#             for tool_call in submit_tool_outputs.tool_calls:
#                 function_name = tool_call.function.name
#                 print(f"Tool call: {function_name}")

#                 if function_name == "get_current_balance":
#                     print("Calling balance API...")
#                     response = requests.post(
#                         balance_api_url,
#                         headers={
#                             "Authorization": f"Bearer {access_token}",
#                             "Content-Type": "application/json",
#                         },
#                         json={},
#                         timeout=10,
#                     )

#                     if response.status_code != 200:
#                         output = json.dumps(
#                             {
#                                 "error": "balance_api_error",
#                                 "status_code": response.status_code,
#                                 "body": response.text,
#                             }
#                         )
#                         print(f"Balance API error: {response.status_code} - {response.text}")
#                     else:
#                         print(f"Balance API response: {response.text}")
#                         output = json.dumps(response.json())

#                     tool_outputs.append(
#                         {
#                             "tool_call_id": tool_call.id,
#                             "output": output,
#                         }
#                     )

#             run = client.runs.submit_tool_outputs(
#                 thread_id=thread.id,
#                 run_id=run.id,
#                 tool_outputs=tool_outputs,
#             )
#         else:
#             run = client.runs.get(
#                 thread_id=thread.id,
#                 run_id=run.id,
#             )

#     if run.status != "completed":
#         return JSONResponse(
#             {"error": f"run failed: {run.status}"},
#             status_code=500,
#         )

#     last_text = client.messages.get_last_message_text_by_role(
#         thread_id=thread.id,
#         role="assistant",
#     )

#     print(type(client.messages))

#     last_5_messages = client.messages.list(thread_id=thread.id, limit=5)
#     print("Last 5 messages in the thread:")
#     for msg in last_5_messages:
#         print(f"{msg.role}: {msg.content}")

#     return {"response": last_text}


@app.post('/chat')
async def chat(message: Message, request: Request):
    user_message = message.message

    if not user_message:
        return JSONResponse({'error': 'message is required'}, status_code=400)

    access_token = request.session.get('access_token')
    if not access_token:
        return JSONResponse({'error': 'user is not authenticated'}, status_code=401)

    thread = client.threads.create()

    log_file = LOG_DIR / f'agent-run-{thread.id}-{int(time.time())}.jsonl'

    append_jsonl(
        log_file,
        {
            'timestamp': utc_now_iso(),
            'type': 'thread_created',
            'thread_id': thread.id,
        },
    )

    client.messages.create(
        thread_id=thread.id,
        role='user',
        content=user_message,
    )

    append_jsonl(
        log_file,
        {
            'timestamp': utc_now_iso(),
            'type': 'user_message_created',
            'thread_id': thread.id,
            'content': user_message,
        },
    )

    handler = LoggingAgentEventHandler(
        client=client,
        thread_id=thread.id,
        log_file=log_file,
        access_token=access_token,
        balance_api_url=balance_api_url,
    )

    with client.runs.stream(
        thread_id=thread.id,
        agent_id=BALANCE_AGENT_ID,
        event_handler=handler,
    ) as stream:
        stream.until_done()

    run = handler.final_run

    if run is None and handler.run_id:
        run = client.runs.get(
            thread_id=thread.id,
            run_id=handler.run_id,
        )

    if run is None:
        return JSONResponse(
            {
                'error': 'run not found',
                'thread_id': thread.id,
                'log_file': str(log_file),
            },
            status_code=500,
        )

    if str(getattr(run, 'status', '')).lower().endswith('completed') is False:
        return JSONResponse(
            {
                'error': f"run failed: {getattr(run, 'status', None)}",
                'thread_id': thread.id,
                'run_id': getattr(run, 'id', None),
                'last_error': safe_serialize(getattr(run, 'last_error', None)),
                'stream_error': safe_serialize(handler.last_error),
                'log_file': str(log_file),
                'status': str(getattr(run, 'status', None)),
            },
            status_code=500,
        )

    last_text = client.messages.get_last_message_text_by_role(
        thread_id=thread.id,
        role='assistant',
    )

    append_jsonl(
        log_file,
        {
            'timestamp': utc_now_iso(),
            'type': 'final_response',
            'thread_id': thread.id,
            'run_id': getattr(run, 'id', None),
            'response': last_text,
        },
    )

    return {
        'response': last_text,
        'thread_id': thread.id,
        'run_id': getattr(run, 'id', None),
        'log_file': str(log_file),
        'status': str(getattr(run, 'status', None)),
    }
