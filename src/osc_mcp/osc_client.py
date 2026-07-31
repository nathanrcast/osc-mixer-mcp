"""OSC UDP client: one persistent socket, correlated queries, subscriptions.

All three console families reply to the *source port* of the sender, so a
single bound socket serves sends, queries and subscription streams. A daemon
receiver thread demultiplexes replies by OSC address, which is what makes
`query_many` (and any state push) possible.
"""

from __future__ import annotations

import queue
import socket
import threading
import time
from typing import Any, Callable

from pythonosc.osc_message import OscMessage, ParseError
from pythonosc.osc_message_builder import OscMessageBuilder

DEFAULT_TIMEOUT = 0.5
_RECV_BUFSIZE = 65535
# Cadence of the receive loop's wakeups, so stop() is responsive.
_POLL_INTERVAL = 0.2


def build_message(address: str, args: list[Any]) -> bytes:
    """Encode an OSC message. Values keep their Python types."""
    builder = OscMessageBuilder(address=address)
    for arg in args:
        builder.add_arg(arg)
    return builder.build().dgram


class OscClient:
    """Persistent OSC/UDP client with address-correlated request/response."""

    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("", 0))
        self._sock.settimeout(_POLL_INTERVAL)

        self._lock = threading.Lock()
        self._pending: dict[str, list[queue.Queue]] = {}
        self._meter_handlers: dict[str, Callable[[list[Any]], None]] = {}
        self._stop = threading.Event()

        self._receiver = threading.Thread(
            target=self._receive_loop, name="osc-receiver", daemon=True
        )
        self._receiver.start()

        self._keepalive: threading.Thread | None = None
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Receive path
    # ------------------------------------------------------------------

    def _receive_loop(self) -> None:
        while not self._stop.is_set():
            try:
                data, (src_ip, _) = self._sock.recvfrom(_RECV_BUFSIZE)
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed under us
            if src_ip != self.ip:
                continue  # drop spoofed/unrelated packets
            try:
                message = OscMessage(data)
            except (ParseError, ValueError, IndexError, UnicodeDecodeError):
                continue  # malformed packet, ignore rather than crash
            self._dispatch(message.address, list(message.params))

    def _dispatch(self, address: str, args: list[Any]) -> None:
        with self._lock:
            waiters = self._pending.get(address)
            waiter = waiters.pop(0) if waiters else None
            if waiters is not None and not waiters:
                del self._pending[address]
            handler = self._meter_handlers.get(address)
        if waiter is not None:
            waiter.put(args)
        if handler is not None:
            handler(args)

    def _register(self, address: str) -> queue.Queue:
        pipe: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._pending.setdefault(address, []).append(pipe)
        return pipe

    def _unregister(self, address: str, pipe: queue.Queue) -> None:
        with self._lock:
            waiters = self._pending.get(address)
            if not waiters:
                return
            if pipe in waiters:
                waiters.remove(pipe)
            if not waiters:
                del self._pending[address]

    # ------------------------------------------------------------------
    # Send path
    # ------------------------------------------------------------------

    def send(self, address: str, *args: Any) -> None:
        """Send an OSC message. Fire and forget."""
        if not self._connected:
            raise ConnectionError("Not connected to mixer")
        self._sock.sendto(build_message(address, list(args)), (self.ip, self.port))

    def query(
        self, address: str, timeout: float = DEFAULT_TIMEOUT
    ) -> list[Any] | None:
        """Ask for a parameter's current value.

        All three families reply to a no-argument message with the current
        value. Returns the reply args, or None on timeout. The reply is matched
        by address, so a stray push for a different parameter cannot satisfy it.
        """
        results = self.query_many([address], timeout=timeout)
        return results.get(address)

    def query_many(
        self, addresses: list[str], timeout: float = DEFAULT_TIMEOUT
    ) -> dict[str, list[Any] | None]:
        """Query many parameters in one round-trip window.

        Every request goes out first, then replies are collected until the
        deadline. Turns an O(n) stall into roughly one timeout -- the
        difference between ~30 s and ~1 s when syncing an X32's strip names.
        """
        if not self._connected:
            raise ConnectionError("Not connected to mixer")

        unique = list(dict.fromkeys(addresses))
        pipes = {address: self._register(address) for address in unique}
        try:
            for address in unique:
                self.send(address)

            results: dict[str, list[Any] | None] = {}
            deadline = time.monotonic() + timeout
            for address in unique:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    results[address] = None
                    continue
                try:
                    results[address] = pipes[address].get(timeout=remaining)
                except queue.Empty:
                    results[address] = None
            return results
        finally:
            for address, pipe in pipes.items():
                self._unregister(address, pipe)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def start_keepalive(self, address: str, args: list[Any], interval: float) -> None:
        """Renew a subscription on a timer until disconnect.

        On WING only one client may hold the subscription, so this can displace
        another controller -- callers gate it behind read-only mode.
        """
        if self._keepalive is not None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.send(address, *args)
                except (OSError, ConnectionError):
                    return
                if self._stop.wait(interval):
                    return

        self._keepalive = threading.Thread(
            target=loop, name="osc-keepalive", daemon=True
        )
        self._keepalive.start()

    def add_meter_handler(
        self, address: str, handler: Callable[[list[Any]], None]
    ) -> None:
        with self._lock:
            self._meter_handlers[address] = handler

    def remove_meter_handler(self, address: str) -> None:
        with self._lock:
            self._meter_handlers.pop(address, None)

    # ------------------------------------------------------------------

    def disconnect(self) -> None:
        """Tear down the socket and both threads."""
        if not self._connected:
            return
        self._connected = False
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        for thread in (self._receiver, self._keepalive):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
        self._keepalive = None
