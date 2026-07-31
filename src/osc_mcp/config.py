"""Persistent configuration and safety gates for the OSC MCP server."""

from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".osc_mcp"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Networks the server is allowed to target. Restricting this means a
# compromised or prompt-injected MCP client cannot aim the OSC sender
# at arbitrary hosts on the LAN. Override for a venue subnet with
# OSC_MCP_ALLOWED_NETWORKS="192.168.10.0/24,10.1.2.0/24".
DEFAULT_NETWORKS = ("192.168.1.0/24", "127.0.0.0/8")

ALLOWED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network(n) for n in DEFAULT_NETWORKS
]


def _env_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None:
    raw = os.environ.get("OSC_MCP_ALLOWED_NETWORKS", "").strip()
    if not raw:
        return None
    networks = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part))
        except ValueError:
            continue  # ignore malformed entries rather than open up the LAN
    return networks or None


def allowed_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Effective allowlist: the env override if set, else ALLOWED_NETWORKS."""
    return _env_networks() or ALLOWED_NETWORKS


def is_allowed_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in allowed_networks())


def is_read_only() -> bool:
    """Block every write when OSC_MCP_READ_ONLY is set to a truthy value.

    Worth setting during a live service, and required on WING if another
    controller already holds the console's single OSC subscription.
    """
    return os.environ.get("OSC_MCP_READ_ONLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def save_mixer_address(ip: str, port: int, model: str | None = None) -> None:
    """Persist the mixer address (and detected model) to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str | int] = {"ip": ip, "port": port}
    if model:
        payload["model"] = model
    CONFIG_FILE.write_text(json.dumps(payload))


def load_mixer_address() -> tuple[str, int] | None:
    """Load the last-used mixer address from disk.

    Returns (ip, port) or None if the config is missing or corrupt.
    """
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return (data["ip"], data["port"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return None


def load_mixer_model() -> str | None:
    """Load the last detected model string, or None if unknown."""
    try:
        data = json.loads(CONFIG_FILE.read_text())
        model = data.get("model")
        return model if isinstance(model, str) and model else None
    except (FileNotFoundError, json.JSONDecodeError, AttributeError, TypeError):
        return None
