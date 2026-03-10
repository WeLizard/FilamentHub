from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


class BotStateStore:
    def __init__(self, path: str | Path, agents: list[str]) -> None:
        self.path = Path(path).resolve()
        self.agents = tuple(agents)
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _default_agent_state(self) -> dict[str, Any]:
        return {
            "session_ref": None,
            "last_output": "",
            "last_run_at": None,
        }

    def _default_thread_state(self, chat_id: int, topic_id: int | None) -> dict[str, Any]:
        return {
            "chat_id": chat_id,
            "topic_id": topic_id,
            "active_agent": None,
            "agents": {name: self._default_agent_state() for name in self.agents},
        }

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        data = raw if isinstance(raw, dict) else {}
        threads = data.get("threads")
        normalized = {
            "version": 1,
            "threads": threads if isinstance(threads, dict) else {},
        }
        for thread_state in normalized["threads"].values():
            if not isinstance(thread_state, dict):
                continue
            agents = thread_state.get("agents")
            if not isinstance(agents, dict):
                agents = {}
                thread_state["agents"] = agents
            for agent in self.agents:
                current = agents.get(agent)
                if not isinstance(current, dict):
                    agents[agent] = self._default_agent_state()
                    continue
                current.setdefault("session_ref", None)
                current.setdefault("last_output", "")
                current.setdefault("last_run_at", None)
            if thread_state.get("active_agent") not in self.agents:
                thread_state["active_agent"] = None
        return normalized

    def _read_locked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._normalize(None)
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return self._normalize(None)
        return self._normalize(raw)

    def _write_locked(self, data: dict[str, Any]) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            try:
                os.replace(str(temp_path), str(self.path))
            except PermissionError:
                with self.path.open("w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

    def ensure_thread(self, thread_key: str, chat_id: int, topic_id: int | None) -> dict[str, Any]:
        with self._lock:
            data = self._read_locked()
            threads = data["threads"]
            if thread_key not in threads or not isinstance(threads[thread_key], dict):
                threads[thread_key] = self._default_thread_state(chat_id, topic_id)
                self._write_locked(data)
            else:
                threads[thread_key].setdefault("chat_id", chat_id)
                threads[thread_key]["topic_id"] = topic_id
            return copy.deepcopy(threads[thread_key])

    def get_thread_state(self, thread_key: str, chat_id: int, topic_id: int | None) -> dict[str, Any]:
        return self.ensure_thread(thread_key, chat_id, topic_id)

    def set_active_agent(self, thread_key: str, chat_id: int, topic_id: int | None, agent: str | None) -> dict[str, Any]:
        with self._lock:
            data = self._read_locked()
            threads = data["threads"]
            state = threads.setdefault(thread_key, self._default_thread_state(chat_id, topic_id))
            state["chat_id"] = chat_id
            state["topic_id"] = topic_id
            state["active_agent"] = agent if agent in self.agents else None
            self._write_locked(data)
            return copy.deepcopy(state)

    def update_agent_state(
        self,
        thread_key: str,
        chat_id: int,
        topic_id: int | None,
        agent: str,
        *,
        session_ref: str | None | object = ...,
        last_output: str | object = ...,
        last_run_at: str | None | object = ...,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._read_locked()
            threads = data["threads"]
            state = threads.setdefault(thread_key, self._default_thread_state(chat_id, topic_id))
            state["chat_id"] = chat_id
            state["topic_id"] = topic_id
            agent_state = state["agents"].setdefault(agent, self._default_agent_state())
            if session_ref is not ...:
                agent_state["session_ref"] = session_ref
            if last_output is not ...:
                agent_state["last_output"] = last_output
            if last_run_at is not ...:
                agent_state["last_run_at"] = last_run_at
            self._write_locked(data)
            return copy.deepcopy(state)

    def reset_agent(self, thread_key: str, chat_id: int, topic_id: int | None, agent: str) -> dict[str, Any]:
        with self._lock:
            data = self._read_locked()
            threads = data["threads"]
            state = threads.setdefault(thread_key, self._default_thread_state(chat_id, topic_id))
            state["chat_id"] = chat_id
            state["topic_id"] = topic_id
            state["agents"][agent] = self._default_agent_state()
            if state.get("active_agent") == agent:
                state["active_agent"] = None
            self._write_locked(data)
            return copy.deepcopy(state)

    def reset_thread(self, thread_key: str, chat_id: int, topic_id: int | None) -> dict[str, Any]:
        with self._lock:
            data = self._read_locked()
            data["threads"][thread_key] = self._default_thread_state(chat_id, topic_id)
            self._write_locked(data)
            return copy.deepcopy(data["threads"][thread_key])
