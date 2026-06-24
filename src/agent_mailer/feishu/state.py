"""Lightweight JSON persistence for bridge dedup and thread continuity."""

import json
from pathlib import Path

_MAX_IDS = 2000


class BridgeState:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {
            "feishu_message_ids": [],
            "pushed_broker_message_ids": [],
            "active_thread_id": None,
        }
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @property
    def active_thread_id(self) -> str | None:
        return self.data.get("active_thread_id")

    def set_active_thread(self, thread_id: str | None) -> None:
        self.data["active_thread_id"] = thread_id
        self.save()

    def is_feishu_message_seen(self, message_id: str) -> bool:
        return message_id in self.data["feishu_message_ids"]

    def record_feishu_message(self, message_id: str) -> None:
        ids: list[str] = self.data["feishu_message_ids"]
        if message_id in ids:
            return
        ids.append(message_id)
        if len(ids) > _MAX_IDS:
            self.data["feishu_message_ids"] = ids[-_MAX_IDS:]
        self.save()

    def is_broker_message_pushed(self, message_id: str) -> bool:
        return message_id in self.data["pushed_broker_message_ids"]

    def record_broker_message_pushed(self, message_id: str) -> None:
        ids: list[str] = self.data["pushed_broker_message_ids"]
        if message_id in ids:
            return
        ids.append(message_id)
        if len(ids) > _MAX_IDS:
            self.data["pushed_broker_message_ids"] = ids[-_MAX_IDS:]
        self.save()
