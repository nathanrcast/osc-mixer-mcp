"""OSC UDP client wrapper for send and query operations."""

from __future__ import annotations

import socket
import struct
import time
from typing import Any

from pythonosc.udp_client import SimpleUDPClient


class OscClient:
    """Wraps python-osc SimpleUDPClient with connection state and query support."""

    def __init__(self, ip: str, port: int = 10024) -> None:
        self.ip = ip
        self.port = port
        self._client = SimpleUDPClient(ip, port)
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    def send(self, address: str, *args: Any) -> None:
        """Send an OSC message."""
        if not self._connected:
            raise ConnectionError("Not connected to mixer")
        self._client.send_message(address, list(args) if args else [])

    def query(self, address: str, timeout: float = 0.5) -> list[Any] | None:
        """Query a parameter by sending an empty OSC message and listening for the response.

        The XR18 replies with the current value when you send a parameter path
        with no arguments. Returns the response args list, or None on timeout.

        Drops packets from sources other than self.ip (spoofing defense) and
        returns None if the response fails to parse (malformed packet).
        """
        if not self._connected:
            raise ConnectionError("Not connected to mixer")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", 0))

        try:
            self._send_raw(sock, address)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                sock.settimeout(remaining)
                try:
                    data, (src_ip, _) = sock.recvfrom(4096)
                except socket.timeout:
                    return None
                if src_ip != self.ip:
                    continue  # drop spoofed/unrelated packets
                try:
                    return self._parse_osc_response(data)
                except (ValueError, IndexError, UnicodeDecodeError, struct.error):
                    return None
        finally:
            sock.close()

    def _send_raw(self, sock: socket.socket, address: str) -> None:
        """Send a raw OSC message with no arguments through the given socket."""
        addr_bytes = address.encode("ascii")
        addr_padded = addr_bytes + b"\x00" * (4 - len(addr_bytes) % 4)
        type_tag = b",\x00\x00\x00"
        message = addr_padded + type_tag
        sock.sendto(message, (self.ip, self.port))

    @staticmethod
    def _parse_osc_response(data: bytes) -> list[Any]:
        """Parse a simple OSC response message, returning the argument list."""
        addr_end = data.index(b"\x00")
        offset = addr_end + (4 - addr_end % 4)

        if offset >= len(data) or data[offset : offset + 1] != b",":
            return []

        type_tag_end = data.index(b"\x00", offset)
        type_tags = data[offset + 1 : type_tag_end].decode("ascii")
        offset = type_tag_end + (4 - type_tag_end % 4)

        args: list[Any] = []
        for tag in type_tags:
            if tag == "f":
                (val,) = struct.unpack(">f", data[offset : offset + 4])
                args.append(val)
                offset += 4
            elif tag == "i":
                (val,) = struct.unpack(">i", data[offset : offset + 4])
                args.append(val)
                offset += 4
            elif tag == "s":
                str_end = data.index(b"\x00", offset)
                args.append(data[offset:str_end].decode("ascii"))
                offset = str_end + (4 - str_end % 4)

        return args

    def disconnect(self) -> None:
        """Mark client as disconnected."""
        self._connected = False
