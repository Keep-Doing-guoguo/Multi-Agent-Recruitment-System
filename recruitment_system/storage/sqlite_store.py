from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class ConversationStore:
    """SQLite persistence with two tables: conversations and messages."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Open a store at db_path and ensure its schema exists."""
        self.db_path = Path(db_path or os.getenv("RECRUITMENT_DB_PATH", "data/recruitment.sqlite3"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def init_schema(self) -> None:
        """Create conversations and messages tables when they do not exist."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    current_state_json TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    run_id TEXT,
                    route TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_run_id ON messages(run_id)")

    def create_conversation(
        self,
        title: str = "招聘会话",
        current_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert and return a new conversation record."""
        conversation_id = str(uuid4())
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    id, title, current_state_json, summary, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, '', ?, ?, ?)
                """,
                (
                    conversation_id,
                    title,
                    self._dumps(current_state or {}),
                    self._dumps(metadata or {}),
                    now,
                    now,
                ),
            )
        return self.get_conversation(conversation_id)  # type: ignore[return-value]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """Return one conversation by id, or None when it does not exist."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, current_state_json, summary, metadata_json, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._conversation_from_row(row)

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent conversations ordered by updated_at descending."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, current_state_json, summary, metadata_json, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._conversation_from_row(row) for row in rows]

    def update_conversation_state(
        self,
        conversation_id: str,
        current_state: dict[str, Any],
        title: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist the latest structured state for a conversation."""
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"conversation_not_found: {conversation_id}")

        next_title = title or conversation["title"]
        next_summary = summary if summary is not None else conversation["summary"]
        next_metadata = metadata if metadata is not None else conversation["metadata"]
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, current_state_json = ?, summary = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_title,
                    self._dumps(current_state),
                    next_summary,
                    self._dumps(next_metadata),
                    now,
                    conversation_id,
                ),
            )
        return self.get_conversation(conversation_id)  # type: ignore[return-value]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        message_type: str,
        run_id: str | None = None,
        route: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one message or run snapshot to a conversation."""
        if self.get_conversation(conversation_id) is None:
            raise ValueError(f"conversation_not_found: {conversation_id}")

        message_id = str(uuid4())
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, role, content, message_type, run_id, route, payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    message_type,
                    run_id,
                    route,
                    self._dumps(payload or {}),
                    now,
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return self.get_message(message_id)  # type: ignore[return-value]

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Return one persisted message by id."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, conversation_id, role, content, message_type, run_id, route, payload_json, created_at
                FROM messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        return self._message_from_row(row)

    def list_messages(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return messages for a conversation in chronological order."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, message_type, run_id, route, payload_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        """Create a SQLite connection configured for row access by column name."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _conversation_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a conversations table row into an API-friendly dictionary."""
        return {
            "id": row["id"],
            "title": row["title"],
            "current_state": self._loads(row["current_state_json"]),
            "summary": row["summary"],
            "metadata": self._loads(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _message_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a messages table row into an API-friendly dictionary."""
        return {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "message_type": row["message_type"],
            "run_id": row["run_id"],
            "route": row["route"],
            "payload": self._loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def _dumps(self, value: dict[str, Any]) -> str:
        """Serialize JSON payloads with compact separators and Chinese text preserved."""
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _loads(self, value: str) -> dict[str, Any]:
        """Deserialize a JSON object string, returning an empty dict for non-objects."""
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}

    def _now(self) -> str:
        """Return the current UTC timestamp as an ISO-8601 string."""
        return datetime.now(timezone.utc).isoformat()
