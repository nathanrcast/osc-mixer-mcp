"""Persistent configuration for the OSC MCP server."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".osc_mcp"
CONFIG_FILE = CONFIG_DIR / "config.json"


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
