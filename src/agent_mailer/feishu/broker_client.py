"""HTTP client for broker admin routes (session-authenticated)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BrokerClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        self._session_token: str | None = None
        self._op_address: str | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    def _auth_headers(self) -> dict[str, str]:
        if not self._session_token:
            return {}
        return {"Authorization": f"Bearer {self._session_token}"}

    async def login(self) -> None:
        resp = await self._client.post(
            "/users/login",
            json={"username": self.username, "password": self.password},
        )
        resp.raise_for_status()
        self._session_token = resp.json()["token"]
        logger.info("Broker session established for user %s", self.username)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        extra_headers = dict(kwargs.pop("headers", {}))
        headers = {**extra_headers, **self._auth_headers()}
        resp = await self._client.request(method, path, headers=headers, **kwargs)
        if resp.status_code == 401:
            logger.warning("Broker session expired; re-authenticating")
            await self.login()
            headers = {**extra_headers, **self._auth_headers()}
            resp = await self._client.request(method, path, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    async def ensure_human_operator(self) -> dict[str, str]:
        resp = await self._request("GET", "/admin/human-operator")
        data = resp.json()
        self._op_address = data["address"]
        return data

    @property
    def op_address(self) -> str:
        if not self._op_address:
            raise RuntimeError("human-operator address not loaded; call ensure_human_operator()")
        return self._op_address

    async def inbox_unread(self, address: str | None = None) -> list[dict[str, Any]]:
        addr = address or self.op_address
        resp = await self._request("GET", f"/admin/messages/inbox/{addr}")
        data = resp.json()
        if isinstance(data, dict) and "messages" in data:
            return data["messages"]
        return data

    async def mark_read(self, message_id: str) -> dict[str, Any]:
        resp = await self._request("PATCH", f"/admin/messages/{message_id}/read")
        return resp.json()

    async def send_message(
        self,
        *,
        to_agent: str,
        action: str,
        subject: str,
        body: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "to_agent": to_agent,
            "action": action,
            "subject": subject,
            "body": body,
        }
        if parent_id:
            payload["parent_id"] = parent_id
        resp = await self._request("POST", "/admin/messages/send", json=payload)
        return resp.json()

    async def get_thread(self, thread_id: str) -> list[dict[str, Any]]:
        resp = await self._request("GET", f"/admin/messages/thread/{thread_id}")
        return resp.json()
