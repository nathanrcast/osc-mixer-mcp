"""Tests for MCP server tools with mocked OscClient."""

from unittest.mock import MagicMock, patch

import pytest

from osc_mcp import xair
from osc_mcp import server


@pytest.fixture(autouse=True)
def reset_server_state():
    """Reset global state before each test."""
    server._client = None
    server._registry = xair.NameRegistry()
    yield
    server._client = None
    server._registry = xair.NameRegistry()


def _mock_client() -> MagicMock:
    """Create a mock OscClient and install it as the server's client."""
    mock = MagicMock()
    mock.connected = True
    server._client = mock
    return mock


class TestConnectMixer:
    @patch("osc_mcp.server.config")
    @patch("osc_mcp.server.OscClient")
    def test_connect_creates_client(self, MockOscClient, mock_config):
        MockOscClient.return_value.query.return_value = ["XR18"]
        result = server.connect_mixer("192.168.1.1", 10024)
        MockOscClient.assert_called_once_with("192.168.1.1", 10024)
        assert "Connected" in result
        mock_config.save_mixer_address.assert_called_once_with("192.168.1.1", 10024)

    @patch("osc_mcp.server.config")
    @patch("osc_mcp.server.OscClient")
    def test_connect_default_port(self, MockOscClient, mock_config):
        MockOscClient.return_value.query.return_value = ["XR18"]
        server.connect_mixer("192.168.1.200")
        MockOscClient.assert_called_once_with("192.168.1.200", 10024)

    @patch("osc_mcp.server.config")
    @patch("osc_mcp.server.OscClient")
    def test_connect_unreachable_returns_warning(self, MockOscClient, mock_config):
        MockOscClient.return_value.query.return_value = None
        result = server.connect_mixer("192.168.1.1")
        assert "not responding" in result
        mock_config.save_mixer_address.assert_not_called()


class TestNotConnected:
    @patch("osc_mcp.server.config")
    def test_no_stored_config(self, mock_config):
        mock_config.load_mixer_address.return_value = None
        with pytest.raises(ConnectionError, match="Use connect_mixer"):
            server.set_channel_fader(1, 0.0)

    @patch("osc_mcp.server.OscClient")
    @patch("osc_mcp.server.config")
    def test_stored_ip_not_responding(self, mock_config, MockOscClient):
        mock_config.load_mixer_address.return_value = ("192.168.0.2", 10024)
        MockOscClient.return_value.query.return_value = None
        with pytest.raises(ConnectionError, match="192.168.0.2:10024"):
            server.set_channel_fader(1, 0.0)

    @patch("osc_mcp.server.OscClient")
    @patch("osc_mcp.server.config")
    def test_auto_connect_from_stored_config(self, mock_config, MockOscClient):
        mock_config.load_mixer_address.return_value = ("192.168.0.2", 10024)
        mock_instance = MockOscClient.return_value
        mock_instance.query.return_value = ["XR18"]
        mock_instance.send = MagicMock()
        result = server.set_channel_fader(1, 0.0)
        MockOscClient.assert_called_once_with("192.168.0.2", 10024)
        assert "0 dB" in result


class TestChannelTools:
    def test_set_channel_fader(self):
        mock = _mock_client()
        result = server.set_channel_fader(1, 0.0)
        mock.send.assert_called_once_with("/ch/01/mix/fader", 0.75)
        assert "0 dB" in result

    def test_set_channel_fader_with_name(self):
        mock = _mock_client()
        server._registry.assign_name("channel", 1, "Kick")
        result = server.set_channel_fader("Kick", -10.0)
        mock.send.assert_called_once_with("/ch/01/mix/fader", 0.5)
        assert "Channel 1" in result

    def test_set_channel_mute(self):
        mock = _mock_client()
        server.set_channel_mute(3, True)
        mock.send.assert_called_once_with("/ch/03/mix/on", 0)

    def test_set_channel_unmute(self):
        mock = _mock_client()
        server.set_channel_mute(3, False)
        mock.send.assert_called_once_with("/ch/03/mix/on", 1)

    def test_get_channel_fader(self):
        mock = _mock_client()
        mock.query.return_value = [0.75]
        result = server.get_channel_fader(1)
        mock.query.assert_called_once_with("/ch/01/mix/fader")
        assert "0.0 dB" in result

    def test_get_channel_fader_timeout(self):
        mock = _mock_client()
        mock.query.return_value = None
        result = server.get_channel_fader(1)
        assert "timeout" in result

    def test_invalid_channel_number(self):
        _mock_client()
        with pytest.raises(ValueError, match="Channel must be"):
            server.set_channel_fader(19, 0.0)

    def test_unresolved_channel_name(self):
        _mock_client()
        with pytest.raises(ValueError, match="Unknown channel"):
            server.set_channel_fader("NonExistent", 0.0)


class TestBusTools:
    def test_set_bus_fader(self):
        mock = _mock_client()
        result = server.set_bus_fader(2, -10.0)
        mock.send.assert_called_once_with("/bus/2/mix/fader", 0.5)
        assert "-10" in result

    def test_set_bus_fader_with_name(self):
        mock = _mock_client()
        server._registry.assign_name("bus", 2, "Drummer")
        result = server.set_bus_fader("Drummer", 0.0)
        mock.send.assert_called_once_with("/bus/2/mix/fader", 0.75)

    def test_set_bus_mute(self):
        mock = _mock_client()
        server.set_bus_mute(1, True)
        mock.send.assert_called_once_with("/bus/1/mix/on", 0)

    def test_set_channel_send_to_bus(self):
        mock = _mock_client()
        result = server.set_channel_send_to_bus(5, 3, -10.0)
        mock.send.assert_called_once_with("/ch/05/mix/03/level", 0.5)

    def test_set_channel_send_to_bus_with_names(self):
        mock = _mock_client()
        server._registry.assign_name("channel", 1, "Kick")
        server._registry.assign_name("bus", 2, "Drummer")
        server.set_channel_send_to_bus("Kick", "Drummer", 0.0)
        mock.send.assert_called_once_with("/ch/01/mix/02/level", 0.75)

    def test_get_channel_send_to_bus(self):
        mock = _mock_client()
        mock.query.return_value = [0.5]
        result = server.get_channel_send_to_bus(1, 2)
        mock.query.assert_called_once_with("/ch/01/mix/02/level")
        assert "-10.0 dB" in result


class TestMainTools:
    def test_set_main_fader(self):
        mock = _mock_client()
        server.set_main_fader(0.0)
        mock.send.assert_called_once_with("/lr/0/mix/fader", 0.75)

    def test_set_main_mute(self):
        mock = _mock_client()
        server.set_main_mute(True)
        mock.send.assert_called_once_with("/lr/0/mix/on", 0)


class TestEqTools:
    def test_set_channel_eq(self):
        mock = _mock_client()
        server.set_channel_eq(1, 2, 1000.0, 3.0, 1.5)
        assert mock.send.call_count == 3
        mock.send.assert_any_call("/ch/01/eq/2/f", 1000.0)
        mock.send.assert_any_call("/ch/01/eq/2/g", 3.0)
        mock.send.assert_any_call("/ch/01/eq/2/q", 1.5)

    def test_set_channel_eq_on(self):
        mock = _mock_client()
        server.set_channel_eq_on(1, True)
        mock.send.assert_called_once_with("/ch/01/eq/on", 1)

    def test_set_channel_eq_off(self):
        mock = _mock_client()
        server.set_channel_eq_on(1, False)
        mock.send.assert_called_once_with("/ch/01/eq/on", 0)


class TestFxTools:
    def test_set_fx_send_fader(self):
        mock = _mock_client()
        server.set_fx_send_fader(1, 0.0)
        mock.send.assert_called_once_with("/fxsend/1/mix/fader", 0.75)

    def test_set_fx_send_mute(self):
        mock = _mock_client()
        server.set_fx_send_mute(2, True)
        mock.send.assert_called_once_with("/fxsend/2/mix/on", 0)

    def test_invalid_fx_slot(self):
        _mock_client()
        with pytest.raises(ValueError, match="FX slot must be"):
            server.set_fx_send_fader(5, 0.0)


class TestInfoTools:
    def test_get_mixer_info(self):
        mock = _mock_client()
        mock.query.return_value = ["XR18", "1.0", "192.168.1.1"]
        result = server.get_mixer_info()
        mock.query.assert_called_once_with("/xinfo")
        assert "XR18" in result

    def test_get_mixer_info_timeout(self):
        mock = _mock_client()
        mock.query.return_value = None
        result = server.get_mixer_info()
        assert "timeout" in result


class TestRawOsc:
    def test_send_raw_with_args(self):
        mock = _mock_client()
        server.send_raw_osc("/ch/01/mix/fader", [0.5])
        mock.send.assert_called_once_with("/ch/01/mix/fader", 0.5)

    def test_send_raw_no_args(self):
        mock = _mock_client()
        server.send_raw_osc("/xinfo")
        mock.send.assert_called_once_with("/xinfo")

    def test_send_raw_refuses_disallowed_prefix(self):
        mock = _mock_client()
        result = server.send_raw_osc("/-snap/01/load", [1])
        assert "Refused" in result
        mock.send.assert_not_called()

    def test_send_raw_refuses_show_prefix(self):
        mock = _mock_client()
        result = server.send_raw_osc("/-show/current/load")
        assert "Refused" in result
        mock.send.assert_not_called()

    def test_send_raw_refuses_prefs_prefix(self):
        mock = _mock_client()
        result = server.send_raw_osc("/-prefs/ip/addr", ["10.0.0.1"])
        assert "Refused" in result
        mock.send.assert_not_called()


class TestConnectAllowlist:
    @patch("osc_mcp.server.OscClient")
    def test_connect_refuses_out_of_range_ip(self, MockOscClient):
        result = server.connect_mixer("8.8.8.8")
        assert "Refused" in result
        MockOscClient.assert_not_called()

    @patch("osc_mcp.server.OscClient")
    def test_connect_refuses_malformed_ip(self, MockOscClient):
        result = server.connect_mixer("not-an-ip")
        assert "Refused" in result
        MockOscClient.assert_not_called()

    @patch("osc_mcp.server.OscClient")
    def test_auto_connect_refuses_out_of_range_stored_ip(
        self, MockOscClient, tmp_path, monkeypatch
    ):
        from osc_mcp import config as real_config

        monkeypatch.setattr(real_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(real_config, "CONFIG_FILE", tmp_path / "config.json")
        real_config.save_mixer_address("8.8.8.8", 10024)
        with pytest.raises(ConnectionError, match="ALLOWED_NETWORKS"):
            server.set_channel_fader(1, 0.0)
        MockOscClient.assert_not_called()


class TestSyncNames:
    def test_sync_names_populates_registry(self):
        mock = _mock_client()

        def query_side_effect(addr):
            mapping = {
                "/ch/01/config/name": ["Kick"],
                "/ch/02/config/name": ["Snare"],
                "/bus/1/config/name": ["Drums"],
            }
            return mapping.get(addr, [""])

        mock.query.side_effect = query_side_effect
        count = server._sync_names(mock)
        assert count == 3
        assert server._registry.resolve("channel", "Kick") == 1
        assert server._registry.resolve("channel", "Snare") == 2
        assert server._registry.resolve("bus", "Drums") == 1

    def test_sync_names_skips_empty(self):
        mock = _mock_client()
        mock.query.return_value = [""]
        count = server._sync_names(mock)
        assert count == 0
        assert server._registry.list_names("channel") == {}
        assert server._registry.list_names("bus") == {}

    def test_sync_names_skips_none(self):
        mock = _mock_client()
        mock.query.return_value = None
        count = server._sync_names(mock)
        assert count == 0

    def test_sync_names_skips_whitespace_only(self):
        mock = _mock_client()
        mock.query.return_value = ["   "]
        count = server._sync_names(mock)
        assert count == 0

    @patch("osc_mcp.server.config")
    @patch("osc_mcp.server.OscClient")
    def test_connect_mixer_reports_synced_names(self, MockOscClient, mock_config):
        instance = MockOscClient.return_value

        def query_side_effect(addr):
            if addr == "/xinfo":
                return ["XR18"]
            if addr == "/ch/01/config/name":
                return ["Kick"]
            if addr == "/bus/2/config/name":
                return ["Monitor"]
            return [""]

        instance.query.side_effect = query_side_effect
        result = server.connect_mixer("192.168.1.1")
        assert "Connected" in result
        assert "Synced 2 name(s)" in result

    @patch("osc_mcp.server.config")
    @patch("osc_mcp.server.OscClient")
    def test_connect_mixer_no_names_no_sync_message(self, MockOscClient, mock_config):
        instance = MockOscClient.return_value

        def query_side_effect(addr):
            if addr == "/xinfo":
                return ["XR18"]
            return [""]

        instance.query.side_effect = query_side_effect
        result = server.connect_mixer("192.168.1.1")
        assert "Connected" in result
        assert "Synced" not in result


class TestNaming:
    def test_assign_channel_name(self):
        result = server.assign_channel_name(1, "Kick")
        assert "Kick" in result
        assert server._registry.resolve("channel", "Kick") == 1

    def test_assign_bus_name(self):
        result = server.assign_bus_name(2, "Drummer")
        assert "Drummer" in result
        assert server._registry.resolve("bus", "Drummer") == 2

    def test_list_names(self):
        server.assign_channel_name(1, "Kick")
        server.assign_bus_name(2, "Drummer")
        result = server.list_names()
        assert result == {
            "channels": {1: "Kick"},
            "buses": {2: "Drummer"},
        }

    def test_assign_invalid_channel(self):
        with pytest.raises(ValueError):
            server.assign_channel_name(19, "Bad")

    def test_assign_invalid_bus(self):
        with pytest.raises(ValueError):
            server.assign_bus_name(7, "Bad")
