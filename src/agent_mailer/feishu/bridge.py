"""FastAPI app: Feishu webhook (inbound) + broker inbox polling (outbound)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from agent_mailer.feishu.broker_client import BrokerClient
from agent_mailer.feishu.config import FeishuBridgeConfig
from agent_mailer.feishu.feishu_client import FeishuClient
from agent_mailer.feishu.state import BridgeState

logger = logging.getLogger(__name__)


def _normalize_headers(headers: Any) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items()}


async def poll_outbound_once(
    broker: BrokerClient,
    feishu: FeishuClient,
    state: BridgeState,
    config: FeishuBridgeConfig,
) -> None:
    messages = await broker.inbox_unread()
    for msg in reversed(messages):
        msg_id = msg["id"]
        if state.is_broker_message_pushed(msg_id):
            continue
        text = FeishuClient.format_outbound_message(msg)
        await feishu.send_text(config.chat_id, text)
        await broker.mark_read(msg_id)
        state.record_broker_message_pushed(msg_id)
        state.set_active_thread(msg.get("thread_id"))


async def outbound_poll_loop(app: FastAPI) -> None:
    broker: BrokerClient = app.state.broker
    feishu: FeishuClient = app.state.feishu
    state: BridgeState = app.state.state
    config: FeishuBridgeConfig = app.state.config

    while True:
        try:
            await poll_outbound_once(broker, feishu, state, config)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbound poll failed")
        await asyncio.sleep(config.poll_interval)


async def handle_inbound_message(
    broker: BrokerClient,
    feishu: FeishuClient,
    state: BridgeState,
    config: FeishuBridgeConfig,
    event: dict[str, Any],
) -> None:
    message = event.get("message") or {}
    message_id = message.get("message_id")
    if not message_id:
        return

    if message.get("chat_id") != config.chat_id:
        return

    sender = event.get("sender") or {}
    if sender.get("sender_type") == "app":
        return

    if message.get("message_type") != "text":
        return

    if not await feishu.is_bot_mentioned(message):
        return

    if state.is_feishu_message_seen(message_id):
        return

    text = FeishuClient.extract_text(message)
    if not text:
        return

    state.record_feishu_message(message_id)

    parent_id: str | None = None
    action = "send"
    subject = "Feishu"

    thread_id = state.active_thread_id
    if thread_id:
        thread_msgs = await broker.get_thread(thread_id)
        if thread_msgs:
            parent_id = thread_msgs[-1]["id"]
            action = "reply"
            subject = ""

    result = await broker.send_message(
        to_agent=config.pm_address,
        action=action,
        subject=subject,
        body=text,
        parent_id=parent_id,
    )
    state.set_active_thread(result.get("thread_id"))


def create_app(
    config: FeishuBridgeConfig | None = None,
    *,
    enable_poll: bool = True,
    broker: BrokerClient | None = None,
    feishu: FeishuClient | None = None,
    state: BridgeState | None = None,
) -> FastAPI:
    bridge_config = config or FeishuBridgeConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = bridge_config
        app.state.broker = broker or BrokerClient(
            bridge_config.broker_base_url,
            bridge_config.operator_username,
            bridge_config.operator_password,
        )
        app.state.feishu = feishu or FeishuClient(
            bridge_config.app_id,
            bridge_config.app_secret,
            bridge_config.verification_token,
            bridge_config.encrypt_key,
        )
        app.state.state = state or BridgeState(bridge_config.state_path)

        if broker is None:
            await app.state.broker.login()
            await app.state.broker.ensure_human_operator()
        if feishu is None:
            await app.state.feishu.bot_open_id()

        poll_task = None
        if enable_poll:
            poll_task = asyncio.create_task(outbound_poll_loop(app))
        logger.info(
            "Feishu bridge started (broker=%s, chat=%s, pm=%s)",
            bridge_config.broker_base_url,
            bridge_config.chat_id,
            bridge_config.pm_address,
        )
        try:
            yield
        finally:
            if poll_task is not None:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
            await app.state.broker.aclose()
            await app.state.feishu.aclose()

    app = FastAPI(title="Agent Mailer Feishu Bridge", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/feishu/webhook")
    async def feishu_webhook(request: Request):
        body_bytes = await request.body()
        body = body_bytes.decode("utf-8")
        feishu: FeishuClient = request.app.state.feishu
        broker: BrokerClient = request.app.state.broker
        state: BridgeState = request.app.state.state
        config: FeishuBridgeConfig = request.app.state.config

        try:
            payload = feishu.parse_event(_normalize_headers(request.headers), body)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        if payload.get("type") == "url_verification":
            return {"challenge": payload["challenge"]}

        header = payload.get("header") or {}
        if header.get("event_type") != "im.message.receive_v1":
            return {"ok": True}

        try:
            await handle_inbound_message(
                broker, feishu, state, config, payload.get("event") or {}
            )
        except Exception:
            logger.exception("Inbound Feishu message handling failed")
            raise HTTPException(status_code=500, detail="Inbound handling failed") from None

        return {"ok": True}

    return app
