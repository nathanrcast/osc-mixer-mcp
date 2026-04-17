"""Tests for OscClient with mocked UDP socket."""

from unittest.mock import MagicMock, patch

import pytest

from osc_mcp.osc_client import OscClient


class TestOscClient:
    def test_send_dispatches_message(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            client = OscClient("192.168.1.1", 10024)
            client.send("/ch/01/mix/fader", 0.75)

            mock_instance.send_message.assert_called_once_with(
                "/ch/01/mix/fader", [0.75]
            )

    def test_send_no_args(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            client = OscClient("192.168.1.1")
            client.send("/xinfo")

            mock_instance.send_message.assert_called_once_with("/xinfo", [])

    def test_send_multiple_args(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            client = OscClient("192.168.1.1")
            client.send("/some/path", 1.0, "hello", 42)

            mock_instance.send_message.assert_called_once_with(
                "/some/path", [1.0, "hello", 42]
            )

    def test_connection_state(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient"):
            client = OscClient("192.168.1.1")
            assert client.connected is True

            client.disconnect()
            assert client.connected is False

    def test_send_when_disconnected_raises(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient"):
            client = OscClient("192.168.1.1")
            client.disconnect()

            with pytest.raises(ConnectionError, match="Not connected"):
                client.send("/ch/01/mix/fader", 0.5)

    def test_query_when_disconnected_raises(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient"):
            client = OscClient("192.168.1.1")
            client.disconnect()

            with pytest.raises(ConnectionError, match="Not connected"):
                client.query("/ch/01/mix/fader")

    def test_client_stores_ip_and_port(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient"):
            client = OscClient("10.0.0.1", 12345)
            assert client.ip == "10.0.0.1"
            assert client.port == 12345

    def test_default_port(self):
        with patch("osc_mcp.osc_client.SimpleUDPClient"):
            client = OscClient("10.0.0.1")
            assert client.port == 10024


class TestQuerySourceFilter:
    """Ensure query() drops packets from unexpected source IPs."""

    def _make_sock_mock(self, packets):
        """Return a mock socket whose recvfrom yields the given packets in order."""
        mock_sock = MagicMock()
        mock_sock.recvfrom.side_effect = packets
        return mock_sock

    def test_query_drops_spoofed_packet_and_falls_back(self):
        """A packet from a wrong IP is ignored; next packet from mixer is accepted."""
        import struct

        # OSC response for /ch/01/mix/fader with one float arg = 0.5
        addr = b"/ch/01/mix/fader\x00\x00\x00\x00"
        type_tag = b",f\x00\x00"
        payload = struct.pack(">f", 0.5)
        real_packet = addr + type_tag + payload

        with patch("osc_mcp.osc_client.SimpleUDPClient"), \
                patch("osc_mcp.osc_client.socket.socket") as MockSocket:
            mock_sock = self._make_sock_mock([
                (b"garbage", ("10.9.9.9", 55555)),   # spoofed, drop
                (real_packet, ("192.168.1.1", 10024)),  # real mixer
            ])
            MockSocket.return_value = mock_sock
            client = OscClient("192.168.1.1")
            result = client.query("/ch/01/mix/fader")
            assert result == [pytest.approx(0.5)]

    def test_query_returns_none_on_malformed_packet(self):
        """Malformed packet from the expected IP is swallowed, returns None."""
        import socket as _socket

        with patch("osc_mcp.osc_client.SimpleUDPClient"), \
                patch("osc_mcp.osc_client.socket.socket") as MockSocket:
            mock_sock = MagicMock()
            # First call returns junk, second raises timeout
            mock_sock.recvfrom.side_effect = [
                (b"\xff\xff\xff\xff", ("192.168.1.1", 10024)),
            ]
            MockSocket.return_value = mock_sock
            client = OscClient("192.168.1.1")
            result = client.query("/ch/01/mix/fader")
            assert result is None
