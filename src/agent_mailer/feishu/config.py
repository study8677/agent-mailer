"""Environment-driven configuration for the Feishu bridge process."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(_project_root / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required for the Feishu bridge")
    return value


@dataclass(frozen=True)
class FeishuBridgeConfig:
    app_id: str
    app_secret: str
    verification_token: str
    encrypt_key: str
    chat_id: str
    broker_base_url: str
    operator_username: str
    operator_password: str
    pm_address: str
    poll_interval: float
    state_path: Path
    bridge_host: str
    bridge_port: int

    @classmethod
    def from_env(cls) -> "FeishuBridgeConfig":
        return cls(
            app_id=_require("FEISHU_APP_ID"),
            app_secret=_require("FEISHU_APP_SECRET"),
            verification_token=_require("FEISHU_VERIFICATION_TOKEN"),
            encrypt_key=os.environ.get("FEISHU_ENCRYPT_KEY", "").strip(),
            chat_id=_require("FEISHU_CHAT_ID"),
            broker_base_url=os.environ.get(
                "AGENT_MAILER_BASE_URL", "http://127.0.0.1:9800"
            ).rstrip("/"),
            operator_username=_require("AGENT_MAILER_OPERATOR_USER"),
            operator_password=_require("AGENT_MAILER_OPERATOR_PASSWORD"),
            pm_address=_require("FEISHU_PM_ADDRESS"),
            poll_interval=float(os.environ.get("FEISHU_POLL_INTERVAL", "3")),
            state_path=Path(
                os.environ.get(
                    "FEISHU_BRIDGE_STATE_PATH",
                    str(_project_root / ".feishu-bridge" / "state.json"),
                )
            ),
            bridge_host=os.environ.get("FEISHU_BRIDGE_HOST", "0.0.0.0"),
            bridge_port=int(os.environ.get("FEISHU_BRIDGE_PORT", "9810")),
        )
