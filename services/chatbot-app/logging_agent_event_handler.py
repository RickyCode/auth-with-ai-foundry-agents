import json
import time
from pathlib import Path
from typing import Any

import requests
from azure.ai.agents.models import (
    AgentEventHandler,
    MessageDeltaChunk,
    RunStep,
    ThreadMessage,
    ThreadRun,
)

from .utils import append_jsonl, safe_serialize, utc_now_iso


class LoggingAgentEventHandler(AgentEventHandler[str]):
    def __init__(
        self,
        client,
        thread_id: str,
        log_file: Path,
        access_token: str,
        balance_api_url: str,
    ) -> None:
        super().__init__()
        self.client = client
        self.thread_id = thread_id
        self.log_file = log_file
        self.access_token = access_token
        self.balance_api_url = balance_api_url
        self.run_id: str | None = None
        self.final_run: ThreadRun | None = None
        self.assistant_text_parts: list[str] = []
        self.last_error: Any = None

    def _log(self, record: dict) -> None:
        append_jsonl(
            self.log_file,
            {
                'timestamp': utc_now_iso(),
                **record,
            },
        )

    def on_event(self, event_type, event_data, *args, **kwargs) -> None:
        self._log(
            {
                'event_type': str(event_type),
                'event_data_type': type(event_data).__name__ if event_data is not None else None,
                'data': safe_serialize(event_data),
            }
        )

    def on_message_delta(self, delta: MessageDeltaChunk) -> None:
        text_value = None
        try:
            if hasattr(delta, 'text') and delta.text is not None:
                text_value = delta.text
        except Exception:
            text_value = None
        if text_value:
            self.assistant_text_parts.append(str(text_value))
        self._log(
            {
                'type': 'message_delta',
                'delta': safe_serialize(delta),
            }
        )

    def on_message_done(self, message: ThreadMessage) -> None:
        self._log(
            {
                'type': 'message_done',
                'message_id': getattr(message, 'id', None),
                'role': getattr(message, 'role', None),
                'status': getattr(message, 'status', None),
                'content': safe_serialize(getattr(message, 'content', None)),
            }
        )

    def on_run_step(self, step: RunStep) -> None:
        step_run_id = getattr(step, 'run_id', None)
        if step_run_id:
            self.run_id = step_run_id
        self._log(
            {
                'type': 'run_step',
                'step_id': getattr(step, 'id', None),
                'run_id': step_run_id,
                'step_status': getattr(step, 'status', None),
                'step_data': safe_serialize(step),
            }
        )

    def on_run_step_done(self, step: RunStep) -> None:
        step_run_id = getattr(step, 'run_id', None)
        if step_run_id:
            self.run_id = step_run_id
        self._log(
            {
                'type': 'run_step_done',
                'step_id': getattr(step, 'id', None),
                'run_id': step_run_id,
                'step_status': getattr(step, 'status', None),
                'step_data': safe_serialize(step),
            }
        )

    def on_run(self, run: ThreadRun) -> None:
        self.run_id = getattr(run, 'id', None)
        self._log(
            {
                'type': 'run',
                'run_id': getattr(run, 'id', None),
                'status': getattr(run, 'status', None),
                'required_action': safe_serialize(getattr(run, 'required_action', None)),
                'last_error': safe_serialize(getattr(run, 'last_error', None)),
            }
        )

    def on_run_done(self, run: ThreadRun) -> None:
        self.run_id = getattr(run, 'id', None)
        self.final_run = run
        self._log(
            {
                'type': 'run_done',
                'run_id': getattr(run, 'id', None),
                'status': getattr(run, 'status', None),
                'last_error': safe_serialize(getattr(run, 'last_error', None)),
            }
        )

    def on_error(self, data: Any) -> None:
        self.last_error = data
        self._log(
            {
                'type': 'stream_error',
                'error': safe_serialize(data),
            }
        )

    def on_done(self) -> None:
        self._log({'type': 'stream_done'})

    def on_unhandled_event(self, event_type, event_data) -> None:
        self._log(
            {
                'type': 'unhandled_event',
                'event_type': str(event_type),
                'data': safe_serialize(event_data),
            }
        )

    def on_run_requires_action(self, run: ThreadRun) -> None:
        self.run_id = getattr(run, 'id', None)
        self._log(
            {
                'type': 'run_requires_action',
                'run_id': getattr(run, 'id', None),
                'status': getattr(run, 'status', None),
                'required_action': safe_serialize(getattr(run, 'required_action', None)),
            }
        )
        tool_outputs = []
        required_action = run.required_action
        submit_tool_outputs = required_action.submit_tool_outputs
        for tool_call in submit_tool_outputs.tool_calls:
            function_name = tool_call.function.name
            function_arguments = getattr(tool_call.function, 'arguments', None)
            self._log(
                {
                    'type': 'tool_call_received',
                    'run_id': getattr(run, 'id', None),
                    'tool_call_id': getattr(tool_call, 'id', None),
                    'function_name': function_name,
                    'function_arguments': safe_serialize(function_arguments),
                }
            )
            if function_name == 'get_current_balance':
                started = time.perf_counter()
                try:
                    response = requests.post(
                        self.balance_api_url,
                        headers={
                            'Authorization': f'Bearer {self.access_token}',
                            'Content-Type': 'application/json',
                        },
                        json={},
                        timeout=10,
                    )
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    self._log(
                        {
                            'type': 'tool_backend_response',
                            'tool_call_id': getattr(tool_call, 'id', None),
                            'function_name': function_name,
                            'status_code': response.status_code,
                            'duration_ms': duration_ms,
                            'response_text': response.text,
                        }
                    )
                    if response.status_code != 200:
                        output = json.dumps(
                            {
                                'error': 'balance_api_error',
                                'status_code': response.status_code,
                                'body': response.text,
                            }
                        )
                    else:
                        output = json.dumps(response.json())
                except Exception as exc:
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    self._log(
                        {
                            'type': 'tool_backend_exception',
                            'tool_call_id': getattr(tool_call, 'id', None),
                            'function_name': function_name,
                            'duration_ms': duration_ms,
                            'exception': str(exc),
                        }
                    )
                    output = json.dumps(
                        {
                            'error': 'balance_api_exception',
                            'message': str(exc),
                        }
                    )
                tool_outputs.append(
                    {
                        'tool_call_id': tool_call.id,
                        'output': output,
                    }
                )
            else:
                tool_outputs.append(
                    {
                        'tool_call_id': tool_call.id,
                        'output': json.dumps(
                            {
                                'error': 'tool_not_implemented',
                                'function_name': function_name,
                            }
                        ),
                    }
                )
        self._log(
            {
                'type': 'submit_tool_outputs',
                'run_id': getattr(run, 'id', None),
                'tool_outputs': safe_serialize(tool_outputs),
            }
        )
        updated_run = self.client.runs.submit_tool_outputs(
            thread_id=self.thread_id,
            run_id=run.id,
            tool_outputs=tool_outputs,
        )
        self.run_id = getattr(updated_run, 'id', self.run_id)
        self.final_run = updated_run
