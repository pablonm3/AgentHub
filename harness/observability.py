"""Telemetry towards an external collector and the Claude Code telemetry environment (spec 5.6).

The copy never starts or stops a stack and never calls Docker: whoever runs the collector keeps
it up. Mode `external` probes the collector port and gives steps the OTEL_* variables while it
answers; mode `off` gives them none.

- probe the collector (4317 by default) and UI (8080 by default) ports
- build the OTEL_* environment for a step
- the SigNoz MCP server registration
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from .paths import Layout

COLLECTOR_PORT_DEFAULT = 4317
UI_PORT_DEFAULT = 8080


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].strip()
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


class Observability:
    def __init__(self, layout: Layout, mode: str = "external"):
        self.layout = layout
        self.mode = mode  # external | off
        self.dir = layout.observability
        # the collector's ports and the SigNoz key live with the private files; a single-root
        # harness keeps them next to otel.env
        env_file = layout.private_root / ".env"
        self.env = _read_env_file(env_file if env_file.is_file() else self.dir / ".env")
        self.collector_port = int(self.env.get("OTLP_GRPC_PORT", COLLECTOR_PORT_DEFAULT))
        self.ui_port = int(self.env.get("SIGNOZ_UI_PORT", UI_PORT_DEFAULT))

    # ------------------------------------------------------------ probes
    @staticmethod
    def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            try:
                return s.connect_ex((host, port)) == 0
            except OSError:
                return False

    def collector_up(self) -> bool:
        return self.port_open(self.collector_port)

    def ui_up(self) -> bool:
        return self.port_open(self.ui_port)

    def ui_url(self) -> str:
        return f"http://localhost:{self.ui_port}"

    def status_text(self) -> str:
        return " · ".join(
            [
                f"mode {self.mode}",
                f"collector :{self.collector_port} {'up' if self.collector_up() else 'down'}",
                f"ui :{self.ui_port} {'up' if self.ui_up() else 'down'}",
            ]
        )

    # ------------------------------------------------------------ telemetry env
    def step_env(self, attrs: dict[str, str]) -> dict[str, str]:
        """OTEL variables for a `claude -p` step: otel.env plus per-step resource attributes."""
        env = _read_env_file(self.dir / "otel.env")
        env.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://localhost:{self.collector_port}")
        env["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(f"{k}={v}" for k, v in attrs.items())
        return env

    def mcp_config(self) -> dict:
        """MCP server registration for the SigNoz MCP server (spec 5.6)."""
        return {
            "mcpServers": {
                "signoz": {
                    "command": self.env.get("SIGNOZ_MCP_BIN", "signoz-mcp-server"),
                    "args": [],
                    "env": {
                        "SIGNOZ_URL": self.ui_url(),
                        "SIGNOZ_API_KEY": self.env.get("SIGNOZ_API_KEY", ""),
                        "LOG_LEVEL": "info",
                    },
                }
            }
        }

    def write_mcp_config(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.mcp_config(), indent=2) + "\n")
        return path


def env_flag_summary(active: bool, reason: str | None) -> str:
    if active:
        return "telemetry: on"
    return f"telemetry: off ({reason})" if reason else "telemetry: off"


def telemetry_env_disabled() -> bool:
    return os.environ.get("HARNESS_NO_TELEMETRY") == "1"
