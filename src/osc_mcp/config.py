"""Persistent configuration for the OSC MCP server."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".osc_mcp"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Networks the server is allowed to target. Restricting this means a
# compromised or prompt-injected MCP client cannot aim the OSC sender
# at arbitrary hosts on the LAN.
ALLOWED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("192.168.1.0/24"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def is_allowed_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in ALLOWED_NETWORKS)


def save_mixer_address(ip: str, port: int) -> None:
    """Persist the mixer IP and port to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"ip": ip, "port": port}))


def load_mixer_address() -> tuple[str, int] | None:
    """Load the last-used mixer address from disk.

    Returns (ip, port) or None if the config is missing or corrupt.
    """
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return (data["ip"], data["port"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return None
