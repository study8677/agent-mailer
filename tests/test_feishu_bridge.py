import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from agent_mailer.feishu.bridge import create_app, handle_inbound_message, poll_outbound_once
from agent_mailer.feishu.broker_client import BrokerClient
from agent_mailer.feishu.config import FeishuBridgeConfig
from agent_mailer.feishu.feishu_client import FeishuClient
from agent_mailer.feishu.state import BridgeState


def _test_config(tmp_path: Path) -> FeishuBridgeConfig:
    return FeishuBridgeConfig(
        app_id="cli_test_app",
        app_secret="cli_test_secret",
        verification_token="verify_token_123",
        encrypt_key="",
        chat_id="oc_test_chat",
        broker_base_url="http://broker.test",
        operator_username="testuser",
        operator_password="test-password-123",
        pm_address="pm@testuser.amp.linkyun.co",
        poll_interval=1.0,
        state_path=tmp_path / "state.json",
        bridge_host="127.0.0.1",
        bridge_port=9810,
    )


def test_bridge_state_dedup_and_thread(tmp_path):
    state = BridgeState(tmp_path / "state.json")
    state.record_feishu_message("fm1")
    assert state.is_feishu_message_seen("fm1")
    state.set_active_thread("thread-abc")
    assert state.active_thread_id == "thread-abc"

    state2 = BridgeState(tmp_path / "state.json")
    assert state2.is_feishu_message_seen("fm1")
    assert state2.active_thread_id == "thread-abc"


def test_feishu_signature_and_url_challenge():
    client = FeishuClient("app", "secret", "verify_token_123")
    body = json.dumps({"type": "url_verification", "challenge": "ch_1", "token": "verify_token_123"})
    timestamp = "1700000000"
    nonce = "nonce"
    signature = hashlib.sha256(f"{timestamp}{nonce}verify_token_123{body}".encode()).hexdigest()
    headers = {
        "x-lark-request-timestamp": timestamp,
        "x-lark-request-nonce": nonce,
        "x-lark-signature": signature,
    }
    payload = client.parse_event(headers, body)
    assert payload["challenge"] == "ch_1"


def test_feishu_signature_rejects_missing_header():
    client = FeishuClient("app", "secret", "verify_token_123")
    body = json.dumps({"header": {"event_type": "im.message.receive_v1"}})
    with pytest.raises(ValueError, match="Missing"):
        client.parse_event({}, body)


def test_feishu_signature_rejects_invalid():
    client = FeishuClient("app", "secret", "verify_token_123")
    body = "{}"
    headers = {
        "x-lark-request-timestamp": "1",
        "x-lark-request-nonce": "n",
        "x-lark-signature": "bad",
    }
    with pytest.raises(ValueError, match="signature"):
        client.parse_event(headers, body)


def test_feishu_extract_text_strips_mentions():
    message = {
        "content": json.dumps({"text": "@_user_1 please review"}),
        "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}],
    }
    assert FeishuClient.extract_text(message) == "please review"


@pytest.mark.asyncio
async def test_handle_inbound_new_thread(tmp_path):
    config = _test_config(tmp_path)
    broker = MagicMock()
    broker.send_message = AsyncMock(
        return_value={"id": "m1", "thread_id": "t-new"}
    )
    broker.get_thread = AsyncMock(return_value=[])

    feishu = MagicMock()
    feishu.is_bot_mentioned = AsyncMock(return_value=True)

    state = BridgeState(config.state_path)
    event = {
        "message": {
            "message_id": "fm-new",
            "chat_id": config.chat_id,
            "message_type": "text",
            "content": json.dumps({"text": "@bot start task"}),
            "mentions": [{"key": "@bot", "id": {"open_id": "ou_bot"}}],
        },
        "sender": {"sender_type": "user"},
    }

    await handle_inbound_message(broker, feishu, state, config, event)

    broker.send_message.assert_awaited_once_with(
        to_agent=config.pm_address,
        action="send",
        subject="Feishu",
        body="start task",
        parent_id=None,
    )
    assert state.active_thread_id == "t-new"
    assert state.is_feishu_message_seen("fm-new")


@pytest.mark.asyncio
async def test_handle_inbound_reply_active_thread(tmp_path):
    config = _test_config(tmp_path)
    broker = MagicMock()
    broker.send_message = AsyncMock(
        return_value={"id": "m2", "thread_id": "t-existing"}
    )
    broker.get_thread = AsyncMock(
        return_value=[{"id": "parent-msg", "thread_id": "t-existing"}]
    )

    feishu = MagicMock()
    feishu.is_bot_mentioned = AsyncMock(return_value=True)

    state = BridgeState(config.state_path)
    state.set_active_thread("t-existing")

    event = {
        "message": {
            "message_id": "fm-reply",
            "chat_id": config.chat_id,
            "message_type": "text",
            "content": json.dumps({"text": "@bot follow up"}),
            "mentions": [{"key": "@bot", "id": {"open_id": "ou_bot"}}],
        },
        "sender": {"sender_type": "user"},
    }

    await handle_inbound_message(broker, feishu, state, config, event)

    broker.send_message.assert_awaited_once_with(
        to_agent=config.pm_address,
        action="reply",
        subject="",
        body="follow up",
        parent_id="parent-msg",
    )


@pytest.mark.asyncio
async def test_handle_inbound_ignores_without_bot_mention(tmp_path):
    config = _test_config(tmp_path)
    broker = MagicMock()
    broker.send_message = AsyncMock()
    feishu = MagicMock()
    feishu.is_bot_mentioned = AsyncMock(return_value=False)
    state = BridgeState(config.state_path)

    event = {
        "message": {
            "message_id": "fm-chat",
            "chat_id": config.chat_id,
            "message_type": "text",
            "content": json.dumps({"text": "just chatting"}),
        },
        "sender": {"sender_type": "user"},
    }

    await handle_inbound_message(broker, feishu, state, config, event)
    broker.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_outbound_once_pushes_and_marks_read(tmp_path):
    config = _test_config(tmp_path)
    broker = MagicMock()
    broker.inbox_unread = AsyncMock(
        return_value=[
            {
                "id": "broker-msg-1",
                "thread_id": "t-out",
                "from_agent": "pm@testuser.amp.linkyun.co",
                "subject": "Update",
                "body": "done",
            }
        ]
    )
    broker.mark_read = AsyncMock()

    feishu = MagicMock()
    feishu.send_text = AsyncMock()

    state = BridgeState(config.state_path)
    await poll_outbound_once(broker, feishu, state, config)

    feishu.send_text.assert_awaited_once()
    broker.mark_read.assert_awaited_once_with("broker-msg-1")
    assert state.is_broker_message_pushed("broker-msg-1")
    assert state.active_thread_id == "t-out"

    await poll_outbound_once(broker, feishu, state, config)
    assert feishu.send_text.await_count == 1


@pytest.mark.asyncio
async def test_broker_client_relogin_on_401():
    client = BrokerClient("http://broker.test", "user", "pass")
    client._session_token = "stale-token"

    responses = [
        httpx.Response(401, request=httpx.Request("GET", "http://broker.test/admin/human-operator")),
        httpx.Response(
            200,
            json={"token": "fresh-token"},
            request=httpx.Request("POST", "http://broker.test/users/login"),
        ),
        httpx.Response(
            200,
            json={"agent_id": "op-id", "address": "human-operator@user.amp.linkyun.co"},
            request=httpx.Request("GET", "http://broker.test/admin/human-operator"),
        ),
    ]

    async def mock_request(method, path, **kwargs):
        return responses.pop(0)

    client._client.request = mock_request  # type: ignore[method-assign]

    data = await client.ensure_human_operator()
    assert data["address"] == "human-operator@user.amp.linkyun.co"
    assert client._session_token == "fresh-token"


@pytest.mark.asyncio
async def test_webhook_url_verification_endpoint(tmp_path):
    config = _test_config(tmp_path)
    feishu = FeishuClient(config.app_id, config.app_secret, config.verification_token)
    broker = MagicMock()

    app = create_app(
        config,
        enable_poll=False,
        broker=broker,
        feishu=feishu,
        state=BridgeState(config.state_path),
    )
    # ASGITransport does not run lifespan; set state for the webhook handler.
    app.state.feishu = feishu
    app.state.broker = broker
    app.state.state = BridgeState(config.state_path)
    app.state.config = config

    body = json.dumps(
        {"type": "url_verification", "challenge": "challenge_xyz", "token": config.verification_token}
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/feishu/webhook", content=body)
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "challenge_xyz"
