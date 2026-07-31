"""Tests for OscClient against a real loopback UDP mixer.

A fake console on 127.0.0.1 exercises the actual socket path, which is the only
way to prove the address correlation the old per-query socket never had.
"""

import socket
import threading
import time

import pytest
from pythonosc.osc_message import OscMessage

from osc_mcp.osc_client import OscClient, build_message


class FakeMixer:
    """Answers OSC queries on loopback, like an X-Air replying to the source port."""

    def __init__(self, responses=None, reply_delay=0.0, extra_pushes=None):
        self.responses = responses or {}
        self.reply_delay = reply_delay
        self.extra_pushes = extra_pushes or []
        self.received: list[tuple[str, list]] = []
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(0.05)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                message = OscMessage(data)
            except Exception:
                continue
            with self._lock:
                self.received.append((message.address, list(message.params)))
            if self.reply_delay:
                time.sleep(self.reply_delay)
            for address, args in self.extra_pushes:
                self._sock.sendto(build_message(address, args), addr)
            if message.address in self.responses and not message.params:
                self._sock.sendto(
                    build_message(message.address, self.responses[message.address]),
                    addr,
                )

    def addresses_received(self) -> list[str]:
        with self._lock:
            return [address for address, _ in self.received]

    def stop(self):
        self._stop.set()
        self._sock.close()
        self._thread.join(timeout=1.0)


@pytest.fixture
def mixer():
    m = FakeMixer(
        responses={
            "/ch/01/mix/fader": [0.75],
            "/ch/02/mix/fader": [0.5],
            "/ch/01/config/name": ["Kick"],
            "/ch/01/mix/on": [1],
            "/xinfo": ["127.0.0.1", "XR18-4C-D9", "XR18", "1.17"],
        }
    )
    yield m
    m.stop()


@pytest.fixture
def client(mixer):
    c = OscClient("127.0.0.1", mixer.port)
    yield c
    c.disconnect()


class TestSend:
    def test_send_reaches_the_mixer(self, client, mixer):
        client.send("/ch/01/mix/fader", 0.75)
        time.sleep(0.15)
        assert ("/ch/01/mix/fader", [pytest.approx(0.75)]) in mixer.received

    def test_send_no_args(self, client, mixer):
        client.send("/xinfo")
        time.sleep(0.15)
        assert "/xinfo" in mixer.addresses_received()

    def test_send_multiple_args(self, client, mixer):
        client.send("/some/path", 1.0, "hello", 42)
        time.sleep(0.15)
        address, params = next(
            item for item in mixer.received if item[0] == "/some/path"
        )
        assert params == [pytest.approx(1.0), "hello", 42]

    def test_send_when_disconnected_raises(self, client):
        client.disconnect()
        with pytest.raises(ConnectionError, match="Not connected"):
            client.send("/ch/01/mix/fader", 0.5)


class TestQuery:
    def test_query_returns_value(self, client):
        assert client.query("/ch/01/mix/fader") == [pytest.approx(0.75)]

    def test_query_string_value(self, client):
        assert client.query("/ch/01/config/name") == ["Kick"]

    def test_query_timeout_returns_none(self, client):
        assert client.query("/ch/09/mix/fader", timeout=0.2) is None

    def test_query_when_disconnected_raises(self, client):
        client.disconnect()
        with pytest.raises(ConnectionError, match="Not connected"):
            client.query("/ch/01/mix/fader")

    def test_client_stores_ip_and_port(self, mixer):
        client = OscClient("127.0.0.1", mixer.port)
        try:
            assert client.ip == "127.0.0.1"
            assert client.port == mixer.port
        finally:
            client.disconnect()

    def test_connection_state(self, client):
        assert client.connected is True
        client.disconnect()
        assert client.connected is False

    def test_disconnect_is_idempotent(self, client):
        client.disconnect()
        client.disconnect()
        assert client.connected is False


class TestCorrelation:
    """The bug the old implementation had: any packet answered any query."""

    def test_unrelated_push_does_not_satisfy_a_query(self):
        # The mixer pushes /ch/05/mix/fader on every message, but never
        # answers /ch/09/mix/fader. The query must time out, not return 0.99.
        mixer = FakeMixer(extra_pushes=[("/ch/05/mix/fader", [0.99])])
        client = OscClient("127.0.0.1", mixer.port)
        try:
            assert client.query("/ch/09/mix/fader", timeout=0.3) is None
        finally:
            client.disconnect()
            mixer.stop()

    def test_correct_value_returned_amid_unrelated_traffic(self):
        mixer = FakeMixer(
            responses={"/ch/01/mix/fader": [0.75]},
            extra_pushes=[("/ch/05/mix/fader", [0.99]), ("/-stat/solosw", [1])],
        )
        client = OscClient("127.0.0.1", mixer.port)
        try:
            assert client.query("/ch/01/mix/fader") == [pytest.approx(0.75)]
        finally:
            client.disconnect()
            mixer.stop()

    def test_replies_are_not_crossed(self, client):
        results = client.query_many(["/ch/01/mix/fader", "/ch/02/mix/fader"])
        assert results["/ch/01/mix/fader"] == [pytest.approx(0.75)]
        assert results["/ch/02/mix/fader"] == [pytest.approx(0.5)]

    def test_packets_from_other_sources_are_dropped(self, client, mixer):
        """A spoofed reply from a different IP must not satisfy the query."""
        spoofer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Bind a second loopback-adjacent source so src_ip differs from mixer's.
        spoofer.bind(("127.0.0.2", 0))
        try:
            listen_port = client._sock.getsockname()[1]
            spoofer.sendto(
                build_message("/ch/09/mix/fader", [0.42]),
                ("127.0.0.1", listen_port),
            )
            # 127.0.0.2 != client.ip ("127.0.0.1"), so it is discarded.
            assert client.query("/ch/09/mix/fader", timeout=0.3) is None
        finally:
            spoofer.close()

    def test_malformed_packet_does_not_crash_the_receiver(self, client, mixer):
        junk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            listen_port = client._sock.getsockname()[1]
            junk.sendto(b"\xff\xff\xff\xff", ("127.0.0.1", listen_port))
            time.sleep(0.1)
            # Receiver survived: a normal query still works.
            assert client.query("/ch/01/mix/fader") == [pytest.approx(0.75)]
        finally:
            junk.close()


class TestQueryMany:
    def test_returns_all_values(self, client):
        results = client.query_many(
            ["/ch/01/mix/fader", "/ch/01/config/name", "/ch/01/mix/on"]
        )
        assert results["/ch/01/mix/fader"] == [pytest.approx(0.75)]
        assert results["/ch/01/config/name"] == ["Kick"]
        assert results["/ch/01/mix/on"] == [1]

    def test_missing_addresses_come_back_none(self, client):
        results = client.query_many(
            ["/ch/01/mix/fader", "/ch/09/mix/fader"], timeout=0.3
        )
        assert results["/ch/01/mix/fader"] == [pytest.approx(0.75)]
        assert results["/ch/09/mix/fader"] is None

    def test_duplicates_collapse(self, client):
        results = client.query_many(["/ch/01/mix/fader", "/ch/01/mix/fader"])
        assert len(results) == 1

    def test_empty_list(self, client):
        assert client.query_many([]) == {}

    def test_is_pipelined_not_sequential(self, client, mixer):
        """20 misses must cost about one timeout, not 20 of them."""
        addresses = [f"/ch/{n:02d}/mix/pan" for n in range(1, 21)]
        started = time.monotonic()
        results = client.query_many(addresses, timeout=0.4)
        elapsed = time.monotonic() - started
        assert all(value is None for value in results.values())
        assert elapsed < 1.0  # sequential would be 20 * 0.4 = 8 s


class TestKeepalive:
    def test_renews_on_the_interval(self, mixer):
        client = OscClient("127.0.0.1", mixer.port)
        try:
            client.start_keepalive("/xremote", [], 0.1)
            time.sleep(0.45)
            assert mixer.addresses_received().count("/xremote") >= 3
        finally:
            client.disconnect()

    def test_stops_on_disconnect(self, mixer):
        client = OscClient("127.0.0.1", mixer.port)
        client.start_keepalive("/xremote", [], 0.1)
        time.sleep(0.25)
        client.disconnect()
        settled = mixer.addresses_received().count("/xremote")
        time.sleep(0.35)
        assert mixer.addresses_received().count("/xremote") == settled

    def test_only_one_keepalive_thread(self, mixer):
        client = OscClient("127.0.0.1", mixer.port)
        try:
            client.start_keepalive("/xremote", [], 0.1)
            first = client._keepalive
            client.start_keepalive("/xremote", [], 0.1)
            assert client._keepalive is first
        finally:
            client.disconnect()


class TestMeterHandlers:
    def test_handler_receives_pushes(self, mixer):
        client = OscClient("127.0.0.1", mixer.port)
        frames = []
        try:
            client.add_meter_handler("/meters/4", frames.append)
            listen_port = client._sock.getsockname()[1]
            pusher = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            pusher.bind(("127.0.0.1", 0))
            pusher.sendto(
                build_message("/meters/4", [b"\x02\x00\x00\x00\x00\x00\x00\x00"]),
                ("127.0.0.1", listen_port),
            )
            time.sleep(0.15)
            pusher.close()
            assert len(frames) == 1
        finally:
            client.disconnect()

    def test_removed_handler_stops_receiving(self, mixer):
        client = OscClient("127.0.0.1", mixer.port)
        frames = []
        try:
            client.add_meter_handler("/meters/4", frames.append)
            client.remove_meter_handler("/meters/4")
            listen_port = client._sock.getsockname()[1]
            pusher = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            pusher.bind(("127.0.0.1", 0))
            pusher.sendto(build_message("/meters/4", [1.0]), ("127.0.0.1", listen_port))
            time.sleep(0.15)
            pusher.close()
            assert frames == []
        finally:
            client.disconnect()


class TestBuildMessage:
    def test_round_trips_through_osc(self):
        dgram = build_message("/ch/01/mix/fader", [0.75])
        message = OscMessage(dgram)
        assert message.address == "/ch/01/mix/fader"
        assert message.params == [pytest.approx(0.75)]

    def test_mixed_types(self):
        message = OscMessage(build_message("/x", [1, "two", 3.0]))
        assert message.params == [1, "two", pytest.approx(3.0)]

    def test_no_args(self):
        message = OscMessage(build_message("/xinfo", []))
        assert message.address == "/xinfo"
        assert message.params == []
