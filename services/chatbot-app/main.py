import os
import re
import time
import json
from pathlib import Path

import dotenv
import requests
from azure.ai.agents import AgentsClient
from azure.core.exceptions import HttpResponseError

# from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from .logging_agent_event_handler import LoggingAgentEventHandler
from .utils import append_jsonl, safe_serialize, utc_now_iso

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
app.mount('/static', StaticFiles(directory='services/chatbot-app/static'), name='static')

ACTIVE_RUN_ID_PATTERN = re.compile(r'run_[A-Za-z0-9]+')


# def _extract_assistant_text(value) -> str:
#     """Extract a plain text representation from an assistant response value.

#     Args:
#         value: Assistant response value returned by the SDK or built locally.

#     Returns:
#         A plain text string safe to log and return in JSON responses.
#     """
#     if value is None:
#         return ''

#     if isinstance(value, str):
#         return value.strip()

#     text_value = getattr(value, 'text', None)
#     if isinstance(text_value, str):
#         return text_value.strip()

#     nested_value = getattr(text_value, 'value', None)
#     if isinstance(nested_value, str):
#         return nested_value.strip()

#     direct_value = getattr(value, 'value', None)
#     if isinstance(direct_value, str):
#         return direct_value.strip()

#     serialized_value = safe_serialize(value)
#     if isinstance(serialized_value, str):
#         return serialized_value.strip()

#     return str(serialized_value).strip()


def _extract_active_run_id(error: HttpResponseError) -> str | None:
    """Extract the active run identifier from an SDK error message.

    Args:
        error: Raised HTTP response error.

    Returns:
        The active run identifier when present in the message.
    """
    message = str(error)
    match = ACTIVE_RUN_ID_PATTERN.search(message)
    if match is None:
        return None

    return match.group(0)


def _create_new_thread(request: Request, log_file: Path | None = None) -> str:
    """Create a new thread and persist it in session.

    Args:
        request: FastAPI request with session support.
        log_file: Optional JSONL log file path.

    Returns:
        The new thread identifier.
    """
    thread = client.threads.create()
    request.session['thread_id'] = thread.id

    if log_file is not None:
        append_jsonl(
            log_file,
            {
                'timestamp': utc_now_iso(),
                'type': 'thread_created',
                'thread_id': thread.id,
            },
        )

    return thread.id


def _get_or_create_thread_id(request: Request) -> tuple[str, bool]:
    """Get an existing thread identifier from session or create a new one.

    Args:
        request: FastAPI request with session support.

    Returns:
        A tuple containing the thread identifier and a flag indicating whether
        the thread was created during the current request.
    """
    session_thread_id = request.session.get('thread_id')
    if session_thread_id:
        return str(session_thread_id), False

    thread_id = _create_new_thread(request=request)

    return thread_id, True


def _wait_for_run_to_finish(thread_id: str, run_id: str, timeout_seconds: int = 8) -> None:
    """Wait until a run reaches a terminal state.

    Args:
        thread_id: Thread identifier.
        run_id: Run identifier.
        timeout_seconds: Maximum wait time in seconds.

    Raises:
        RuntimeError: If the run does not finish before timeout.
    """
    terminal_statuses = {'completed', 'failed', 'cancelled', 'expired', 'incomplete'}
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        run = client.runs.get(thread_id=thread_id, run_id=run_id)
        status = str(getattr(run, 'status', '')).lower()

        if status in terminal_statuses:

            return

        time.sleep(0.75)

    raise RuntimeError(f'active run did not finish in time: {run_id}')


def _create_user_message(
    request: Request,
    thread_id: str,
    user_message: str,
    log_file: Path,
) -> str:
    """Create a user message, recovering if the current thread is blocked.

    Args:
        request: FastAPI request with session support.
        thread_id: Current thread identifier.
        user_message: User message content.
        log_file: JSONL log file path.

    Returns:
        The thread identifier where the message was finally created.

    Raises:
        HttpResponseError: If the SDK rejects the message for a reason other
            than an active run.
    """
    try:
        client.messages.create(
            thread_id=thread_id,
            role='user',
            content=user_message,
        )

        return thread_id
    except HttpResponseError as error:
        active_run_id = _extract_active_run_id(error)
        if active_run_id is None:
            raise

        append_jsonl(
            log_file,
            {
                'timestamp': utc_now_iso(),
                'type': 'active_run_detected',
                'thread_id': thread_id,
                'run_id': active_run_id,
            },
        )

        try:
            _wait_for_run_to_finish(thread_id=thread_id, run_id=active_run_id)
            client.messages.create(
                thread_id=thread_id,
                role='user',
                content=user_message,
            )

            append_jsonl(
                log_file,
                {
                    'timestamp': utc_now_iso(),
                    'type': 'active_run_finished_after_wait',
                    'thread_id': thread_id,
                    'run_id': active_run_id,
                },
            )

            return thread_id
        except RuntimeError:
            previous_thread_id = thread_id
            new_thread_id = _create_new_thread(request=request, log_file=log_file)

            append_jsonl(
                log_file,
                {
                    'timestamp': utc_now_iso(),
                    'type': 'thread_recreated_after_stuck_run',
                    'previous_thread_id': previous_thread_id,
                    'new_thread_id': new_thread_id,
                    'stuck_run_id': active_run_id,
                },
            )

            client.messages.create(
                thread_id=new_thread_id,
                role='user',
                content=user_message,
            )

            return new_thread_id


def _poll_run_until_terminal(
    thread_id: str,
    run_id: str,
    timeout_seconds: int = 20,
    poll_interval_seconds: float = 0.75,
):
    """Poll a run until it reaches a terminal state.

    Args:
        thread_id: Thread identifier.
        run_id: Run identifier.
        timeout_seconds: Maximum wait time in seconds.
        poll_interval_seconds: Delay between polling attempts.

    Returns:
        The latest run object returned by the SDK.

    Raises:
        RuntimeError: If the run does not reach a terminal state in time.
    """
    terminal_status_suffixes = (
        'completed',
        'failed',
        'cancelled',
        'expired',
        'incomplete',
        'requires_action',
    )
    deadline = time.time() + timeout_seconds
    latest_run = None

    while time.time() < deadline:
        latest_run = client.runs.get(
            thread_id=thread_id,
            run_id=run_id,
        )
        current_status = str(getattr(latest_run, 'status', '')).lower()

        if current_status.endswith(terminal_status_suffixes):

            return latest_run

        time.sleep(poll_interval_seconds)

    raise RuntimeError(f'run did not reach a terminal state in time: {run_id}')


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


def _extract_assistant_text(value) -> str:
    """Extract a plain text representation from an assistant response value.

    Args:
        value: Assistant response value returned by the SDK or built locally.

    Returns:
        A plain text string safe to log and return in JSON responses.
    """
    if value is None:
        return ''

    if isinstance(value, str):
        return value.strip()

    text_value = getattr(value, 'text', None)
    if isinstance(text_value, str):
        return text_value.strip()

    nested_value = getattr(text_value, 'value', None)
    if isinstance(nested_value, str):
        return nested_value.strip()

    direct_value = getattr(value, 'value', None)
    if isinstance(direct_value, str):
        return direct_value.strip()

    serialized_value = safe_serialize(value)
    if isinstance(serialized_value, str):
        return serialized_value.strip()

    return str(serialized_value).strip()


# @app.post('/chat')
# async def chat(message: Message, request: Request):
#     user_message = message.message
#     if not user_message:
#         return JSONResponse({'error': 'message is required'}, status_code=400)

#     access_token = request.session.get('access_token')
#     if not access_token:
#         return JSONResponse({'error': 'user is not authenticated'}, status_code=401)

#     thread_id, thread_created = _get_or_create_thread_id(request)
#     log_file = LOG_DIR / f'agent-run-{thread_id}-{int(time.time())}.jsonl'

#     if thread_created:
#         append_jsonl(
#             log_file,
#             {
#                 'timestamp': utc_now_iso(),
#                 'type': 'thread_created',
#                 'thread_id': thread_id,
#             },
#         )

#     thread_id = _create_user_message(
#         request=request,
#         thread_id=thread_id,
#         user_message=user_message,
#         log_file=log_file,
#     )
#     append_jsonl(
#         log_file,
#         {
#             'timestamp': utc_now_iso(),
#             'type': 'user_message_created',
#             'thread_id': thread_id,
#             'content': user_message,
#         },
#     )
#     handler = LoggingAgentEventHandler(
#         client=client,
#         thread_id=thread_id,
#         log_file=log_file,
#         access_token=access_token,
#         balance_api_url=balance_api_url,
#     )

#     with client.runs.stream(
#         thread_id=thread_id,
#         agent_id=BALANCE_AGENT_ID,
#         event_handler=handler,
#     ) as stream:
#         stream.until_done()

#     run = handler.final_run
#     if run is None and handler.run_id:
#         run = _poll_run_until_terminal(
#             thread_id=thread_id,
#             run_id=handler.run_id,
#         )

#     if run is not None and str(getattr(run, 'status', '')).lower().endswith('requires_action'):
#         append_jsonl(
#             log_file,
#             {
#                 'timestamp': utc_now_iso(),
#                 'type': 'requires_action_detected_in_chat',
#                 'thread_id': thread_id,
#                 'run_id': getattr(run, 'id', None),
#                 'status': str(getattr(run, 'status', None)),
#             },
#         )
#         handler.on_run_requires_action(run)
#         run = _poll_run_until_terminal(
#             thread_id=thread_id,
#             run_id=run.id,
#         )

#     assistant_text = _extract_assistant_text(''.join(handler.assistant_text_parts))
#     if not assistant_text:
#         assistant_text = _extract_assistant_text(
#             client.messages.get_last_message_text_by_role(
#                 thread_id=thread_id,
#                 role='assistant',
#             )
#         )

#     if run is None and assistant_text:
#         append_jsonl(
#             log_file,
#             {
#                 'timestamp': utc_now_iso(),
#                 'type': 'final_response',
#                 'thread_id': thread_id,
#                 'run_id': None,
#                 'response': assistant_text,
#                 'status': 'completed_via_stream_fallback',
#             },
#         )

#         return {
#             'thread_id': thread_id,
#             'run_id': None,
#             'status': 'completed_via_stream_fallback',
#             'message': {
#                 'role': 'assistant',
#                 'content': assistant_text,
#             },
#             'log_file': str(log_file),
#         }

#     if run is None:
#         return JSONResponse(
#             {
#                 'error': 'run not found',
#                 'thread_id': thread_id,
#                 'log_file': str(log_file),
#                 'stream_error': safe_serialize(handler.last_error),
#             },
#             status_code=500,
#         )

#     if str(getattr(run, 'status', '')).lower().endswith('completed') is False:
#         return JSONResponse(
#             {
#                 'error': f"run failed: {getattr(run, 'status', None)}",
#                 'thread_id': thread_id,
#                 'run_id': getattr(run, 'id', None),
#                 'last_error': safe_serialize(getattr(run, 'last_error', None)),
#                 'stream_error': safe_serialize(handler.last_error),
#                 'log_file': str(log_file),
#                 'status': str(getattr(run, 'status', None)),
#             },
#             status_code=500,
#         )

#     append_jsonl(
#         log_file,
#         {
#             'timestamp': utc_now_iso(),
#             'type': 'final_response',
#             'thread_id': thread_id,
#             'run_id': getattr(run, 'id', None),
#             'response': assistant_text,
#         },
#     )

#     return {
#         'thread_id': thread_id,
#         'run_id': getattr(run, 'id', None),
#         'status': str(getattr(run, 'status', None)),
#         'message': {
#             'role': 'assistant',
#             'content': assistant_text,
#         },
#         'log_file': str(log_file),
#     }


# @app.post('/chat/reset')
# async def reset_chat(request: Request):
#     previous_thread_id = request.session.pop('thread_id', None)

#     return {
#         'reset': True,
#         'previous_thread_id': previous_thread_id,
#     }


@app.get('/chat/ui', response_class=HTMLResponse)
async def chat_ui():
    print('Current work directory:', os.getcwd())
    return FileResponse(
        # Path('templates/chat.html'),
        Path('services/chatbot-app/templates/chat.html'),
        media_type='text/html',
    )


def _extract_message_text_content(message) -> str:
    """Extract plain text from a thread message content collection.

    Args:
        message: Thread message returned by the SDK.

    Returns:
        A plain text representation of the message content.
    """
    content_items = getattr(message, 'content', None)
    if not content_items:
        return ''

    text_parts: list[str] = []
    for item in content_items:
        item_text = getattr(item, 'text', None)
        if item_text is None:
            continue

        item_value = getattr(item_text, 'value', None)
        if isinstance(item_value, str):
            text_parts.append(item_value)

    return ''.join(text_parts).strip()


def _append_conversation_turn(
    request: Request,
    thread_id: str,
    user_message: str,
    assistant_message: str,
    run_id: str | None,
    log_file: Path,
) -> None:
    """Persist conversation turn metadata in session.

    Args:
        request: FastAPI request with session support.
        thread_id: Thread identifier used for the turn.
        user_message: User message content.
        assistant_message: Assistant message content.
        run_id: Run identifier associated with the assistant response.
        log_file: JSONL log file generated for the turn.
    """
    conversation_turns = request.session.get('conversation_turns', [])
    conversation_turns.append(
        {
            'thread_id': thread_id,
            'user_message': user_message,
            'assistant_message': assistant_message,
            'run_id': run_id,
            'log_file': str(log_file),
            'created_at': utc_now_iso(),
        }
    )
    request.session['conversation_turns'] = conversation_turns


def _read_jsonl_records(log_file_path: str) -> list[dict]:
    """Read JSONL records from a log file.

    Args:
        log_file_path: Log file path stored in session metadata.

    Returns:
        Parsed JSONL records. Returns an empty list when the file does not exist
        or contains invalid rows.
    """
    log_path = Path(log_file_path)
    if not log_path.exists():

        return []

    records: list[dict] = []
    with log_path.open('r', encoding='utf-8') as file:
        for line in file:
            line_value = line.strip()
            if not line_value:
                continue

            try:
                parsed_record = json.loads(line_value)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed_record, dict):
                records.append(parsed_record)

    return records


def _summarize_stream_event(record: dict) -> dict | None:
    """Build a concise UI summary for a stream-related record.

    Args:
        record: Raw JSONL record.

    Returns:
        A concise event summary or None when the record should not be shown.
    """
    event_type = record.get('type')
    timestamp = record.get('timestamp')
    if not event_type or not timestamp:
        return None

    if event_type == 'thread_created':
        summary = 'Conversation thread created.'
    elif event_type == 'user_message_created':
        summary = 'User message accepted.'
    elif event_type == 'run':
        summary = 'Run started.'
    elif event_type == 'run_step':
        step_status = record.get('step_status')
        summary = f'Run step update ({step_status}).' if step_status else 'Run step update.'
    elif event_type == 'run_step_done':
        step_status = record.get('step_status')
        summary = f'Run step finished ({step_status}).' if step_status else 'Run step finished.'
    elif event_type == 'run_requires_action':
        summary = 'Run requires tool output.'
    elif event_type == 'tool_call_received':
        function_name = record.get('function_name')
        summary = f'Tool call requested: {function_name}.' if function_name else 'Tool call requested.'
    elif event_type == 'tool_backend_response':
        function_name = record.get('function_name')
        status_code = record.get('status_code')
        if function_name and status_code is not None:
            summary = f'Tool response received from {function_name} ({status_code}).'
        else:
            summary = 'Tool backend response received.'
    elif event_type == 'tool_backend_exception':
        function_name = record.get('function_name')
        summary = f'Tool execution failed in {function_name}.' if function_name else 'Tool execution failed.'
    elif event_type == 'submit_tool_outputs':
        summary = 'Tool outputs submitted.'
    elif event_type == 'submit_tool_outputs_stream':
        summary = 'Tool outputs submitted through stream.'
    elif event_type == 'message_done':
        summary = 'Assistant message completed.'
    elif event_type == 'message_delta':
        summary = 'Assistant partial response received.'
    elif event_type == 'run_done':
        summary = 'Run finished.'
    elif event_type == 'stream_done':
        summary = 'Stream finished.'
    elif event_type == 'stream_error':
        summary = 'Stream error detected.'
    elif event_type == 'active_run_detected':
        summary = 'Previous run still active.'
    elif event_type == 'active_run_finished_after_wait':
        summary = 'Previous run finished after waiting.'
    elif event_type == 'thread_recreated_after_stuck_run':
        summary = 'Conversation thread recreated after blocked run.'
    elif event_type == 'requires_action_detected_in_chat':
        summary = 'Chat flow detected required action.'
    elif event_type == 'final_response':
        summary = 'Final assistant response prepared.'
    else:
        return None

    return {
        'timestamp': timestamp,
        'event_type': event_type,
        'summary': summary,
    }


def _get_stream_events_for_turn(log_file_path: str) -> list[dict]:
    """Extract concise stream events for a conversation turn.

    Args:
        log_file_path: JSONL log file path associated with the turn.

    Returns:
        A list of concise stream event summaries.
    """
    records = _read_jsonl_records(log_file_path)
    stream_events: list[dict] = []

    for record in records:
        summarized_event = _summarize_stream_event(record)
        if summarized_event is None:
            continue

        stream_events.append(summarized_event)

    return stream_events


@app.get('/chat/history')
async def chat_history(request: Request):
    thread_id = request.session.get('thread_id')
    last_run_id = request.session.get('last_run_id')
    conversation_turns = request.session.get('conversation_turns', [])

    if not thread_id:
        return {
            'thread_id': None,
            'last_run_id': last_run_id,
            'messages': [],
        }

    visible_messages: list[dict] = []

    for turn in conversation_turns:
        if turn.get('thread_id') != thread_id:
            continue

        user_message = turn.get('user_message', '')
        assistant_message = turn.get('assistant_message', '')
        run_id = turn.get('run_id')
        log_file_path = turn.get('log_file')
        created_at = turn.get('created_at')

        visible_messages.append(
            {
                'message_id': None,
                'role': 'user',
                'content': user_message,
                'created_at': created_at,
            }
        )

        visible_messages.append(
            {
                'message_id': None,
                'role': 'assistant',
                'content': assistant_message,
                'created_at': created_at,
                'run_id': run_id,
                'log_file': log_file_path,
                'stream_events': _get_stream_events_for_turn(log_file_path) if log_file_path else [],
            }
        )

    return {
        'thread_id': thread_id,
        'last_run_id': last_run_id,
        'messages': visible_messages,
    }


@app.post('/chat/reset')
async def reset_chat(request: Request):
    previous_thread_id = request.session.pop('thread_id', None)
    previous_run_id = request.session.pop('last_run_id', None)
    request.session.pop('conversation_turns', None)

    return {
        'reset': True,
        'previous_thread_id': previous_thread_id,
        'previous_run_id': previous_run_id,
        'thread_id': None,
        'last_run_id': None,
    }


@app.post('/chat')
async def chat(message: Message, request: Request):
    user_message = message.message
    if not user_message:
        return JSONResponse({'error': 'message is required'}, status_code=400)

    access_token = request.session.get('access_token')
    if not access_token:
        return JSONResponse({'error': 'user is not authenticated'}, status_code=401)

    thread_id, thread_created = _get_or_create_thread_id(request)
    log_file = LOG_DIR / f'agent-run-{thread_id}-{int(time.time())}.jsonl'

    if thread_created:
        append_jsonl(
            log_file,
            {
                'timestamp': utc_now_iso(),
                'type': 'thread_created',
                'thread_id': thread_id,
            },
        )

    thread_id = _create_user_message(
        request=request,
        thread_id=thread_id,
        user_message=user_message,
        log_file=log_file,
    )
    append_jsonl(
        log_file,
        {
            'timestamp': utc_now_iso(),
            'type': 'user_message_created',
            'thread_id': thread_id,
            'content': user_message,
        },
    )
    handler = LoggingAgentEventHandler(
        client=client,
        thread_id=thread_id,
        log_file=log_file,
        access_token=access_token,
        balance_api_url=balance_api_url,
    )

    with client.runs.stream(
        thread_id=thread_id,
        agent_id=BALANCE_AGENT_ID,
        event_handler=handler,
    ) as stream:
        stream.until_done()

    run = handler.final_run
    if run is None and handler.run_id:
        run = _poll_run_until_terminal(
            thread_id=thread_id,
            run_id=handler.run_id,
        )

    if run is not None and str(getattr(run, 'status', '')).lower().endswith('requires_action'):
        append_jsonl(
            log_file,
            {
                'timestamp': utc_now_iso(),
                'type': 'requires_action_detected_in_chat',
                'thread_id': thread_id,
                'run_id': getattr(run, 'id', None),
                'status': str(getattr(run, 'status', None)),
            },
        )
        handler.on_run_requires_action(run)
        run = _poll_run_until_terminal(
            thread_id=thread_id,
            run_id=run.id,
        )

    assistant_text = _extract_assistant_text(''.join(handler.assistant_text_parts))
    if not assistant_text:
        assistant_text = _extract_assistant_text(
            client.messages.get_last_message_text_by_role(
                thread_id=thread_id,
                role='assistant',
            )
        )

    if run is not None:
        request.session['last_run_id'] = getattr(run, 'id', None)

    if run is None and assistant_text:
        _append_conversation_turn(
            request=request,
            thread_id=thread_id,
            user_message=user_message,
            assistant_message=assistant_text,
            run_id=None,
            log_file=log_file,
        )
        append_jsonl(
            log_file,
            {
                'timestamp': utc_now_iso(),
                'type': 'final_response',
                'thread_id': thread_id,
                'run_id': None,
                'response': assistant_text,
                'status': 'completed_via_stream_fallback',
            },
        )

        return {
            'thread_id': thread_id,
            'run_id': None,
            'status': 'completed_via_stream_fallback',
            'message': {
                'role': 'assistant',
                'content': assistant_text,
            },
            'log_file': str(log_file),
        }

    if run is None:
        return JSONResponse(
            {
                'error': 'run not found',
                'thread_id': thread_id,
                'log_file': str(log_file),
                'stream_error': safe_serialize(handler.last_error),
            },
            status_code=500,
        )

    if str(getattr(run, 'status', '')).lower().endswith('completed') is False:
        return JSONResponse(
            {
                'error': f"run failed: {getattr(run, 'status', None)}",
                'thread_id': thread_id,
                'run_id': getattr(run, 'id', None),
                'last_error': safe_serialize(getattr(run, 'last_error', None)),
                'stream_error': safe_serialize(handler.last_error),
                'log_file': str(log_file),
                'status': str(getattr(run, 'status', None)),
            },
            status_code=500,
        )

    _append_conversation_turn(
        request=request,
        thread_id=thread_id,
        user_message=user_message,
        assistant_message=assistant_text,
        run_id=getattr(run, 'id', None),
        log_file=log_file,
    )
    append_jsonl(
        log_file,
        {
            'timestamp': utc_now_iso(),
            'type': 'final_response',
            'thread_id': thread_id,
            'run_id': getattr(run, 'id', None),
            'response': assistant_text,
        },
    )

    return {
        'thread_id': thread_id,
        'run_id': getattr(run, 'id', None),
        'status': str(getattr(run, 'status', None)),
        'message': {
            'role': 'assistant',
            'content': assistant_text,
        },
        'log_file': str(log_file),
    }