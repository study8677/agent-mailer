"""Feishu Open Platform client — token, messaging, and event parsing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        verification_token: str,
        encrypt_key: str = "",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self._client = httpx.AsyncClient(base_url=FEISHU_API_BASE, timeout=30.0)
        self._tenant_token: str | None = None
        self._tenant_token_expires_at: float = 0.0
        self._bot_open_id: str | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_token and now < self._tenant_token_expires_at - 60:
            return self._tenant_token

        resp = await self._client.post(
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu token error: {data}")
        self._tenant_token = data["tenant_access_token"]
        self._tenant_token_expires_at = now + float(data.get("expire", 7200))
        return self._tenant_token

    async def bot_open_id(self) -> str:
        if self._bot_open_id:
            return self._bot_open_id
        token = await self.tenant_access_token()
        resp = await self._client.get(
            "/bot/v3/info",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu bot info error: {data}")
        self._bot_open_id = data["bot"]["open_id"]
        return self._bot_open_id

    async def send_text(self, chat_id: str, text: str) -> None:
        token = await self.tenant_access_token()
        resp = await self._client.post(
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu send message error: {data}")

    def verify_signature(
        self, timestamp: str, nonce: str, body: str, signature: str
    ) -> bool:
        key = self.encrypt_key or self.verification_token
        raw = f"{timestamp}{nonce}{key}{body}"
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, signature)

    def decrypt_payload(self, cipher_text_b64: str) -> dict[str, Any]:
        if not self.encrypt_key:
            raise RuntimeError("FEISHU_ENCRYPT_KEY is required to decrypt events")
        plain = _aes_cbc_decrypt(self.encrypt_key, cipher_text_b64)
        return json.loads(plain)

    def parse_event(
        self,
        headers: dict[str, str],
        body: str,
    ) -> dict[str, Any]:
        timestamp = headers.get("x-lark-request-timestamp", "")
        nonce = headers.get("x-lark-request-nonce", "")
        signature = headers.get("x-lark-signature", "")

        payload = json.loads(body)

        if payload.get("type") == "url_verification":
            token = payload.get("token", "")
            if not token or token != self.verification_token:
                raise ValueError("Invalid Feishu verification token")
            return payload

        if not signature:
            raise ValueError("Missing Feishu request signature")
        if not self.verify_signature(timestamp, nonce, body, signature):
            raise ValueError("Invalid Feishu request signature")

        if "encrypt" in payload:
            payload = self.decrypt_payload(payload["encrypt"])

        header = payload.get("header", {})
        token = header.get("token", "")
        if token and token != self.verification_token:
            raise ValueError("Invalid Feishu event token")

        return payload

    async def is_bot_mentioned(self, message: dict[str, Any]) -> bool:
        bot_id = await self.bot_open_id()
        for mention in message.get("mentions") or []:
            mention_id = mention.get("id") or {}
            if mention_id.get("open_id") == bot_id:
                return True
        return False

    @staticmethod
    def extract_text(message: dict[str, Any]) -> str:
        content_raw = message.get("content") or "{}"
        content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
        text = content.get("text", "")
        for mention in message.get("mentions") or []:
            key = mention.get("key")
            if key:
                text = text.replace(key, "").strip()
        return text.strip()

    @staticmethod
    def format_outbound_message(msg: dict[str, Any]) -> str:
        subject = (msg.get("subject") or "").strip()
        from_agent = msg.get("from_agent") or ""
        body = (msg.get("body") or "").strip()
        lines = []
        if subject:
            lines.append(f"**{subject}**")
        if from_agent:
            lines.append(f"From: `{from_agent}`")
        if body:
            lines.append(body)
        return "\n".join(lines) if lines else "(empty message)"


def _aes_cbc_decrypt(encrypt_key: str, cipher_text_b64: str) -> str:
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise RuntimeError(
            "FEISHU_ENCRYPT_KEY is set but cryptography is not installed; "
            "add the cryptography package to decrypt Feishu events"
        ) from exc

    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    cipher_bytes = base64.b64decode(cipher_text_b64)
    iv = cipher_bytes[:16]
    encrypted = cipher_bytes[16:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    pad_len = padded[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Invalid PKCS7 padding in Feishu payload")
    return padded[:-pad_len].decode("utf-8")
