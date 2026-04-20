from pathlib import Path
import sqlite3

TURN_DB_PATH = Path('logs/conversations/conversation_turns.db')
TURN_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _get_turns_connection() -> sqlite3.Connection:
    """Create a SQLite connection for conversation turns."""
    connection = sqlite3.connect(TURN_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize_turns_database() -> None:
    """Create the SQLite table used to persist conversation turns."""
    with _get_turns_connection() as connection:
        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS conversation_turns (
                turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_message TEXT NOT NULL,
                run_id TEXT,
                log_file TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            '''
        )
        connection.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_conversation_turns_thread_id_created_at
            ON conversation_turns (thread_id, created_at, turn_id)
            '''
        )


def _append_conversation_turn_to_db(
    thread_id: str,
    user_message: str,
    assistant_message: str,
    run_id: str | None,
    log_file: Path,
    created_at: str,
) -> None:
    """Persist a conversation turn in SQLite."""
    with _get_turns_connection() as connection:
        connection.execute(
            '''
            INSERT INTO conversation_turns (
                thread_id,
                user_message,
                assistant_message,
                run_id,
                log_file,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                thread_id,
                user_message,
                assistant_message,
                run_id,
                str(log_file),
                created_at,
            ),
        )


def _read_conversation_turns(thread_id: str) -> list[dict]:
    """Read persisted conversation turns for a thread from SQLite."""
    with _get_turns_connection() as connection:
        rows = connection.execute(
            '''
            SELECT
                thread_id,
                user_message,
                assistant_message,
                run_id,
                log_file,
                created_at
            FROM conversation_turns
            WHERE thread_id = ?
            ORDER BY created_at ASC, turn_id ASC
            ''',
            (thread_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def _delete_conversation_turns(thread_id: str) -> None:
    """Delete persisted conversation turns for a thread from SQLite."""
    with _get_turns_connection() as connection:
        connection.execute(
            '''
            DELETE FROM conversation_turns
            WHERE thread_id = ?
            ''',
            (thread_id,),
        )