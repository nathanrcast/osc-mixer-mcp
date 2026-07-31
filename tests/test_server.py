"""Tests for the MCP tool layer with a mocked OSC client."""

import struct
from unittest.mock import MagicMock

import pytest

from osc_mcp import config, server
from osc_mcp.names import NameRegistry
from osc_mcp.profiles import PROFILES


def _blob(values_db: list[float]) -> bytes:
    raw = [int(round(v * 256)) for v in values_db]
    return struct.pack("<i", len(raw)) + struct.pack(f"<{len(raw)}h", *raw)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    """Give every test a fresh client, profile and name registry."""
    monkeypatch.delenv("OSC_MCP_READ_ONLY", raising=False)
    monkeypatch.delenv("OSC_MCP_ALLOWED_NETWORKS", raising=False)
    server._client = None
    server._profile = None
    server._registry = NameRegistry()
    yield
    server._client = None
    server._profile = None


@pytest.fixture
def client():
    """A connected XR18 with a mock transport."""
    return connect_as("XR18")


def connect_as(model: str) -> MagicMock:
    mock = MagicMock()
    server._client = mock
    server._profile = PROFILES[model]
    return mock


def sent(mock) -> list[tuple]:
    return [call.args for call in mock.send.call_args_list]


# ---------------------------------------------------------------------------
# Connection gating
# ---------------------------------------------------------------------------


class TestNotConnected:
    def test_tool_reports_no_connection(self):
        with pytest.raises(ConnectionError, match="Not connected"):
            server.set_channel_fader(1, -10)

    def test_connect_refuses_disallowed_ip(self):
        result = server.connect_mixer("8.8.8.8")
        assert "Refused" in result
        assert "allowed networks" in result

    def test_connect_refuses_other_rfc1918(self):
        assert "Refused" in server.connect_mixer("10.0.0.5")

    def test_connect_refuses_malformed_ip(self):
        assert "Refused" in server.connect_mixer("not-an-ip")

    def test_env_override_widens_the_allowlist(self, monkeypatch):
        monkeypatch.setenv("OSC_MCP_ALLOWED_NETWORKS", "10.0.0.0/24")
        assert config.is_allowed_ip("10.0.0.5") is True
        assert config.is_allowed_ip("192.168.1.5") is False

    def test_malformed_env_entries_do_not_open_the_lan(self, monkeypatch):
        monkeypatch.setenv("OSC_MCP_ALLOWED_NETWORKS", "not-a-cidr")
        assert config.is_allowed_ip("8.8.8.8") is False


# ---------------------------------------------------------------------------
# Connect and auto-detection
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    return tmp_path


def install_fake_transport(monkeypatch, detected, identity=None):
    """Patch OscClient and detection so connect_mixer runs without a network."""
    mock = MagicMock()
    mock.query_many.return_value = {}
    mock.query.return_value = identity
    monkeypatch.setattr(server, "OscClient", lambda ip, port: mock)
    if detected is None:
        monkeypatch.setattr(server.profiles, "detect", lambda probe: None)
    else:
        monkeypatch.setattr(
            server.profiles, "detect", lambda probe: (detected, identity or [])
        )
    return mock


XR18_IDENTITY = ["192.168.1.50", "XR18-4C-D9", "XR18", "1.17"]


class TestConnect:
    def test_detects_model_and_saves(self, tmp_config, monkeypatch):
        install_fake_transport(monkeypatch, PROFILES["XR18"], XR18_IDENTITY)
        result = server.connect_mixer("192.168.1.50")
        assert "XR18" in result
        assert "1.17" in result
        assert config.load_mixer_address() == ("192.168.1.50", 10024)
        assert config.load_mixer_model() == "XR18"

    def test_port_comes_from_detection_not_a_default(self, tmp_config, monkeypatch):
        """The old code defaulted to 10024; X32 must land on 10023."""
        install_fake_transport(monkeypatch, PROFILES["X32"], ["mixer", "X32", "4.06"])
        assert "X32" in server.connect_mixer("192.168.1.60")
        assert config.load_mixer_address() == ("192.168.1.60", 10023)

    def test_wing_port(self, tmp_config, monkeypatch):
        install_fake_transport(monkeypatch, PROFILES["WING"], ["WING", "3.0.6"])
        server.connect_mixer("192.168.1.70")
        assert config.load_mixer_address() == ("192.168.1.70", 2223)

    def test_wing_caveats_are_surfaced(self, tmp_config, monkeypatch):
        install_fake_transport(monkeypatch, PROFILES["WING"], ["WING", "3.0.6"])
        assert "Caveats" in server.connect_mixer("192.168.1.70")

    def test_nothing_answers(self, tmp_config, monkeypatch):
        install_fake_transport(monkeypatch, None)
        result = server.connect_mixer("192.168.1.99")
        assert "Refused" in result
        assert "No mixer answered" in result
        assert config.load_mixer_address() is None

    def test_unreachable_is_not_saved(self, tmp_config, monkeypatch):
        install_fake_transport(monkeypatch, None)
        server.connect_mixer("192.168.1.99")
        assert config.load_mixer_address() is None

    def test_explicit_port_skips_detection(self, tmp_config, monkeypatch):
        mock = install_fake_transport(monkeypatch, None, ["mixer", "X32", "4.06"])
        result = server.connect_mixer("192.168.1.60", port=10023)
        assert "X32" in result
        assert config.load_mixer_address() == ("192.168.1.60", 10023)
        assert mock.query.called

    def test_explicit_unknown_port_refused(self, tmp_config, monkeypatch):
        install_fake_transport(monkeypatch, None, ["something"])
        assert "Refused" in server.connect_mixer("192.168.1.60", port=9999)

    def test_reports_synced_names(self, tmp_config, monkeypatch):
        mock = install_fake_transport(monkeypatch, PROFILES["XR18"], XR18_IDENTITY)
        mock.query_many.return_value = {"/ch/01/config/name": ["Kick"]}
        assert "Synced 1 name" in server.connect_mixer("192.168.1.50")

    def test_no_sync_message_when_nothing_named(self, tmp_config, monkeypatch):
        install_fake_transport(monkeypatch, PROFILES["XR18"], XR18_IDENTITY)
        assert "Synced" not in server.connect_mixer("192.168.1.50")

    def test_read_only_is_announced(self, tmp_config, monkeypatch):
        monkeypatch.setenv("OSC_MCP_READ_ONLY", "1")
        install_fake_transport(monkeypatch, PROFILES["XR18"], XR18_IDENTITY)
        assert "READ-ONLY" in server.connect_mixer("192.168.1.50")

    def test_keepalive_started_when_writable(self, tmp_config, monkeypatch):
        mock = install_fake_transport(monkeypatch, PROFILES["XR18"], XR18_IDENTITY)
        server.connect_mixer("192.168.1.50")
        mock.start_keepalive.assert_called_once_with("/xremote", [], 9.0)

    def test_keepalive_suppressed_in_read_only(self, tmp_config, monkeypatch):
        """WING allows one subscriber; read-only must not steal it."""
        monkeypatch.setenv("OSC_MCP_READ_ONLY", "1")
        mock = install_fake_transport(monkeypatch, PROFILES["WING"], ["WING", "3.0.6"])
        server.connect_mixer("192.168.1.70")
        mock.start_keepalive.assert_not_called()

    def test_reconnect_replaces_the_old_client(self, tmp_config, monkeypatch):
        previous = MagicMock()
        server._client = previous
        install_fake_transport(monkeypatch, PROFILES["XR18"], XR18_IDENTITY)
        server.connect_mixer("192.168.1.50")
        previous.disconnect.assert_called_once()


class TestAutoReconnect:
    def test_no_stored_config(self, tmp_config):
        with pytest.raises(ConnectionError, match="Use connect_mixer"):
            server._get_client()

    def test_reconnects_from_stored_config(self, tmp_config, monkeypatch):
        config.save_mixer_address("192.168.1.50", 10024, "XR18")
        install_fake_transport(monkeypatch, None, XR18_IDENTITY)
        client = server._get_client()
        assert client is not None
        assert server._profile.model == "XR18"

    def test_refuses_stored_ip_outside_the_allowlist(self, tmp_config):
        config.save_mixer_address("8.8.8.8", 10024, "XR18")
        with pytest.raises(ConnectionError, match="not in the allowed networks"):
            server._get_client()

    def test_stored_ip_not_responding(self, tmp_config, monkeypatch):
        config.save_mixer_address("192.168.1.50", 10024, "XR18")
        install_fake_transport(monkeypatch, None, None)
        with pytest.raises(ConnectionError, match="different IP"):
            server._get_client()

    def test_model_swap_is_rejected(self, tmp_config, monkeypatch):
        """A different console on the saved IP must not be driven silently."""
        config.save_mixer_address("192.168.1.50", 10023, "X32")
        install_fake_transport(monkeypatch, None, ["mixer", "M32", "4.06"])
        with pytest.raises(ConnectionError, match="identifies as M32"):
            server._get_client()


class TestSyncNames:
    def test_populates_the_registry(self, client):
        client.query_many.return_value = {
            "/ch/01/config/name": ["Kick"],
            "/bus/1/config/name": ["Monitors"],
            "/dca/1/config/name": ["Band"],
        }
        count = server._sync_names(client, PROFILES["XR18"])
        assert count == 3
        assert server._registry.resolve("channel", "Kick") == 1
        assert server._registry.resolve("bus", "Monitors") == 1
        assert server._registry.resolve("dca", "Band") == 1

    def test_is_pipelined_not_per_address(self, client):
        """One query_many call, not 26 sequential query() calls."""
        client.query_many.return_value = {}
        server._sync_names(client, PROFILES["XR18"])
        assert client.query_many.call_count == 1
        assert client.query.call_count == 0

    def test_asks_for_every_strip_on_the_model(self, client):
        client.query_many.return_value = {}
        server._sync_names(client, PROFILES["X32"])
        asked = client.query_many.call_args.args[0]
        # 32 channels + 16 buses + 8 DCAs
        assert len(asked) == 56
        assert "/ch/32/config/name" in asked
        assert "/bus/16/config/name" in asked

    def test_skips_empty_and_whitespace(self, client):
        client.query_many.return_value = {
            "/ch/01/config/name": [""],
            "/ch/02/config/name": ["   "],
            "/ch/03/config/name": None,
            "/ch/04/config/name": [],
            "/ch/05/config/name": ["Snare"],
        }
        assert server._sync_names(client, PROFILES["XR18"]) == 1
        assert server._registry.list_names("channel") == {5: "Snare"}

    def test_skips_non_string_replies(self, client):
        client.query_many.return_value = {"/ch/01/config/name": [0.75]}
        assert server._sync_names(client, PROFILES["XR18"]) == 0

    def test_duplicate_names_are_skipped(self, client):
        client.query_many.return_value = {
            "/ch/01/config/name": ["Vox"],
            "/ch/02/config/name": ["Vox"],
        }
        assert server._sync_names(client, PROFILES["XR18"]) == 1

    def test_clears_stale_names_from_a_previous_mixer(self, client):
        server._registry.assign_name("channel", 9, "OldDesk")
        client.query_many.return_value = {"/ch/01/config/name": ["Kick"]}
        server._sync_names(client, PROFILES["XR18"])
        assert server._registry.list_names("channel") == {1: "Kick"}


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


class TestChannelFader:
    def test_sends_normalized_value(self, client):
        result = server.set_channel_fader(1, 0.0)
        assert sent(client) == [("/ch/01/mix/fader", pytest.approx(0.75))]
        assert "0.0 dB" in result

    def test_neg_inf(self, client):
        server.set_channel_fader(1, -90)
        assert sent(client) == [("/ch/01/mix/fader", 0.0)]

    def test_resolves_a_name(self, client):
        server.assign_channel_name(3, "Kick")
        server.set_channel_fader("Kick", -10)
        assert sent(client)[0][0] == "/ch/03/mix/fader"

    def test_resolves_a_numeric_string(self, client):
        server.set_channel_fader("3", -10)
        assert sent(client)[0][0] == "/ch/03/mix/fader"

    def test_rejects_out_of_range_channel(self, client):
        with pytest.raises(ValueError, match="1-16"):
            server.set_channel_fader(17, -10)

    def test_rejects_zero(self, client):
        with pytest.raises(ValueError):
            server.set_channel_fader(0, -10)

    def test_unknown_name_raises(self, client):
        with pytest.raises(ValueError, match="Unknown channel name"):
            server.set_channel_fader("Trombone", -10)

    def test_get_fader_converts_back(self, client):
        client.query.return_value = [0.75]
        assert "0.0 dB" in server.get_channel_fader(1)

    def test_get_fader_timeout(self, client):
        client.query.return_value = None
        assert "timeout" in server.get_channel_fader(1)

    def test_get_fader_empty_reply(self, client):
        client.query.return_value = []
        assert "-90.0 dB" in server.get_channel_fader(1)


class TestChannelMute:
    def test_xair_mute_sends_zero(self, client):
        server.set_channel_mute(1, True)
        assert sent(client) == [("/ch/01/mix/on", 0)]

    def test_xair_unmute_sends_one(self, client):
        server.set_channel_mute(1, False)
        assert sent(client) == [("/ch/01/mix/on", 1)]

    def test_wing_polarity_is_inverted(self):
        mock = connect_as("WING")
        server.set_channel_mute(1, True)
        assert sent(mock) == [("/ch/1/mute", 1)]

    def test_x32_matches_xair(self):
        mock = connect_as("X32")
        server.set_channel_mute(1, True)
        assert sent(mock) == [("/ch/01/mix/on", 0)]


class TestChannelExtras:
    def test_pan_centre(self, client):
        server.set_channel_pan(1, 0)
        assert sent(client) == [("/ch/01/mix/pan", pytest.approx(0.5))]

    def test_pan_hard_left(self, client):
        server.set_channel_pan(1, -100)
        assert sent(client) == [("/ch/01/mix/pan", 0.0)]

    def test_gain_is_normalized(self, client):
        server.set_channel_gain(1, 24)
        address, value = sent(client)[0]
        assert address == "/headamp/00/gain"
        assert value == pytest.approx(0.5)

    def test_gain_uses_three_digits_on_x32(self):
        mock = connect_as("X32")
        server.set_channel_gain(1, 24)
        assert sent(mock)[0][0] == "/headamp/000/gain"

    def test_phantom_is_not_inverted(self, client):
        server.set_phantom_power(1, True)
        assert sent(client) == [("/headamp/00/phantom", 1)]

    def test_phantom_off(self, client):
        server.set_phantom_power(1, False)
        assert sent(client) == [("/headamp/00/phantom", 0)]

    def test_strip_status(self, client):
        client.query_many.return_value = {
            "/ch/01/config/name": ["Kick"],
            "/ch/01/mix/fader": [0.75],
            "/ch/01/mix/on": [1],
            "/ch/01/mix/pan": [0.5],
        }
        status = server.get_strip_status(1)
        assert status["name"] == "Kick"
        assert status["level_db"] == pytest.approx(0.0)
        assert status["muted"] is False
        assert status["pan"] == pytest.approx(0.0)

    def test_strip_status_decodes_mute_per_model(self):
        mock = connect_as("WING")
        mock.query_many.return_value = {
            "/ch/1/$name": ["Vox"],
            "/ch/1/fdr": [-10.0],
            "/ch/1/mute": [1],
            "/ch/1/pan": [0.0],
        }
        assert server.get_strip_status(1)["muted"] is True

    def test_strip_status_handles_timeouts(self, client):
        client.query_many.return_value = {
            "/ch/01/config/name": None,
            "/ch/01/mix/fader": None,
            "/ch/01/mix/on": None,
            "/ch/01/mix/pan": None,
        }
        status = server.get_strip_status(1)
        assert status["level_db"] is None
        assert status["muted"] is None


# ---------------------------------------------------------------------------
# Buses, main, DCAs
# ---------------------------------------------------------------------------


class TestBusesAndMain:
    def test_bus_fader_xair_padding(self, client):
        server.set_bus_fader(1, 0.0)
        assert sent(client)[0][0] == "/bus/1/mix/fader"

    def test_bus_fader_x32_padding(self):
        mock = connect_as("X32")
        server.set_bus_fader(1, 0.0)
        assert sent(mock)[0][0] == "/bus/01/mix/fader"

    def test_bus_mute(self, client):
        server.set_bus_mute(3, True)
        assert sent(client) == [("/bus/3/mix/on", 0)]

    def test_bus_out_of_range(self, client):
        with pytest.raises(ValueError, match="1-6"):
            server.set_bus_fader(7, 0.0)

    def test_x32_allows_more_buses(self):
        connect_as("X32")
        server.set_bus_fader(16, 0.0)  # no raise

    def test_bus_name_resolution(self, client):
        server.assign_bus_name(2, "Drummer")
        server.set_bus_fader("Drummer", -6)
        assert sent(client)[0][0] == "/bus/2/mix/fader"

    def test_send_to_bus(self, client):
        server.set_channel_send_to_bus(1, 2, -12)
        assert sent(client)[0][0] == "/ch/01/mix/02/level"

    def test_get_send_to_bus(self, client):
        client.query.return_value = [0.75]
        assert "0.0 dB" in server.get_channel_send_to_bus(1, 2)

    def test_get_send_timeout(self, client):
        client.query.return_value = None
        assert "timeout" in server.get_channel_send_to_bus(1, 2)

    def test_main_fader_per_family(self):
        for model, address in [
            ("XR18", "/lr/mix/fader"),
            ("X32", "/main/st/mix/fader"),
            ("WING", "/main/1/fdr"),
        ]:
            mock = connect_as(model)
            server.set_main_fader(-6)
            assert sent(mock)[0][0] == address

    def test_main_mute(self, client):
        server.set_main_mute(True)
        assert sent(client) == [("/lr/mix/on", 0)]


class TestDcas:
    def test_dca_fader(self, client):
        server.set_dca_fader(1, 0.0)
        assert sent(client)[0][0] == "/dca/1/fader"

    def test_dca_mute(self, client):
        server.set_dca_mute(1, True)
        assert sent(client) == [("/dca/1/on", 0)]

    def test_dca_out_of_range_on_xr18(self, client):
        with pytest.raises(ValueError, match="1-4"):
            server.set_dca_fader(5, 0.0)

    def test_wing_has_sixteen(self):
        mock = connect_as("WING")
        server.set_dca_fader(16, 0.0)
        assert sent(mock)[0][0] == "/dca/16/fdr"

    def test_dca_name_resolution(self, client):
        server._registry.assign_name("dca", 2, "Band")
        server.set_dca_fader("Band", -3)
        assert sent(client)[0][0] == "/dca/2/fader"


# ---------------------------------------------------------------------------
# EQ
# ---------------------------------------------------------------------------


class TestEq:
    def test_values_are_normalized_not_raw(self, client):
        """Regression: 1 kHz / +3 dB / Q 2 must not be sent as 1000.0/3.0/2.0."""
        server.set_channel_eq(1, band=2, frequency_hz=1000, gain_db=3, q=2)
        calls = dict(sent(client))
        assert calls["/ch/01/eq/2/f"] == pytest.approx(0.5663, abs=0.001)
        assert calls["/ch/01/eq/2/g"] == pytest.approx(0.6)
        assert calls["/ch/01/eq/2/q"] == pytest.approx(0.459, abs=0.001)
        assert all(value <= 1.0 for value in calls.values())

    def test_wing_takes_real_units(self):
        mock = connect_as("WING")
        server.set_channel_eq(1, band=2, frequency_hz=1000, gain_db=3, q=2)
        calls = dict(sent(mock))
        assert calls["/ch/1/eq/2/f"] == 1000
        assert calls["/ch/1/eq/2/g"] == 3

    def test_band_out_of_range(self, client):
        with pytest.raises(ValueError, match="1-4"):
            server.set_channel_eq(1, band=5, frequency_hz=1000, gain_db=0, q=2)

    def test_wing_has_six_bands(self):
        connect_as("WING")
        server.set_channel_eq(1, band=6, frequency_hz=1000, gain_db=0, q=2)

    def test_eq_on_is_not_inverted(self, client):
        server.set_channel_eq_on(1, True)
        assert sent(client) == [("/ch/01/eq/on", 1)]

    def test_eq_off(self, client):
        server.set_channel_eq_on(1, False)
        assert sent(client) == [("/ch/01/eq/on", 0)]


# ---------------------------------------------------------------------------
# FX and scenes
# ---------------------------------------------------------------------------


class TestFx:
    def test_fx_send_fader(self, client):
        server.set_fx_send_fader(1, -6)
        assert sent(client)[0][0] == "/fxsend/1/mix/fader"

    def test_fx_slot_out_of_range(self, client):
        with pytest.raises(ValueError, match="1-4"):
            server.set_fx_send_fader(5, -6)

    def test_x32_has_eight_slots(self):
        connect_as("X32")
        server.set_fx_send_fader(8, -6)

    def test_fx_send_mute(self, client):
        server.set_fx_send_mute(2, True)
        assert sent(client) == [("/fxsend/2/mix/on", 0)]


class TestScenes:
    def test_xair_snapshot_recall(self, client):
        server.recall_scene(3)
        assert sent(client) == [("/-snap/load", 3)]

    def test_x32_scene_recall(self):
        mock = connect_as("X32")
        server.recall_scene(3)
        assert sent(mock) == [("/-action/goscene", 3)]

    def test_wing_refuses_rather_than_guessing(self):
        mock = connect_as("WING")
        result = server.recall_scene(3)
        assert "Refused" in result
        assert "not mapped for WING" in result
        assert sent(mock) == []

    def test_scene_name(self, client):
        client.query.return_value = ["Opening"]
        assert "Opening" in server.get_scene_name(1)

    def test_scene_name_unavailable_on_wing(self):
        connect_as("WING")
        assert "Unavailable" in server.get_scene_name(1)


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


class TestBatch:
    def test_applies_multiple_commands(self, client):
        result = server.batch([
            {"op": "channel_fader", "channel": 1, "level_db": 0.0},
            {"op": "channel_mute", "channel": 2, "muted": True},
            {"op": "main_fader", "level_db": -6},
        ])
        assert "Applied 3" in result
        assert [address for address, _ in sent(client)] == [
            "/ch/01/mix/fader",
            "/ch/02/mix/on",
            "/lr/mix/fader",
        ]

    def test_resolves_names(self, client):
        server.assign_channel_name(5, "Snare")
        server.batch([{"op": "channel_fader", "channel": "Snare", "level_db": -3}])
        assert sent(client)[0][0] == "/ch/05/mix/fader"

    def test_unknown_op_sends_nothing(self, client):
        result = server.batch([
            {"op": "channel_fader", "channel": 1, "level_db": 0.0},
            {"op": "teleport", "channel": 1},
        ])
        assert "unknown op" in result
        assert sent(client) == []

    def test_missing_op_key(self, client):
        assert "unknown op" in server.batch([{"channel": 1, "level_db": 0}])

    def test_invalid_command_is_atomic(self, client):
        """A bad command anywhere means nothing is sent."""
        result = server.batch([
            {"op": "channel_fader", "channel": 1, "level_db": 0.0},
            {"op": "channel_fader", "channel": 99, "level_db": 0.0},
        ])
        assert "Refused" in result
        assert sent(client) == []

    def test_missing_key_is_reported(self, client):
        result = server.batch([{"op": "channel_fader", "channel": 1}])
        assert "Refused" in result
        assert sent(client) == []

    def test_non_numeric_level_reported(self, client):
        result = server.batch(
            [{"op": "channel_fader", "channel": 1, "level_db": "loud"}]
        )
        assert "Refused" in result
        assert sent(client) == []

    def test_empty_batch(self, client):
        assert "Applied 0" in server.batch([])

    def test_send_and_dca_ops(self, client):
        server.batch([
            {"op": "send", "channel": 1, "bus": 2, "level_db": -12},
            {"op": "dca_mute", "dca": 1, "muted": False},
            {"op": "bus_fader", "bus": 1, "level_db": -3},
            {"op": "channel_pan", "channel": 1, "pan": -50},
            {"op": "bus_mute", "bus": 1, "muted": True},
            {"op": "dca_fader", "dca": 1, "level_db": 0},
            {"op": "main_mute", "muted": False},
        ])
        assert [address for address, _ in sent(client)] == [
            "/ch/01/mix/02/level",
            "/dca/1/on",
            "/bus/1/mix/fader",
            "/ch/01/mix/pan",
            "/bus/1/mix/on",
            "/dca/1/fader",
            "/lr/mix/on",
        ]

    def test_uses_the_connected_model(self):
        mock = connect_as("X32")
        server.batch([{"op": "bus_fader", "bus": 1, "level_db": 0.0}])
        assert sent(mock)[0][0] == "/bus/01/mix/fader"


# ---------------------------------------------------------------------------
# Raw OSC gating
# ---------------------------------------------------------------------------


class TestRawOsc:
    def test_allows_normal_path(self, client):
        result = server.send_raw_osc("/ch/01/mix/fader", [0.5])
        assert "Sent OSC" in result
        assert sent(client) == [("/ch/01/mix/fader", 0.5)]

    def test_allows_no_args(self, client):
        assert "Sent OSC" in server.send_raw_osc("/xinfo")
        assert sent(client) == [("/xinfo",)]

    def test_denies_node_passthrough(self, client):
        result = server.send_raw_osc("/node", ["/ch/01/mix/fader"])
        assert "Refused (denylist)" in result
        assert sent(client) == []

    def test_denies_network_reconfig(self, client):
        assert "Refused" in server.send_raw_osc("/-prefs/ip/addr", ["10.0.0.1"])
        assert sent(client) == []

    def test_denies_show_wipe(self, client):
        assert "Refused" in server.send_raw_osc("/-action/clearshow")
        assert "Refused" in server.send_raw_osc("/-action/newshow")
        assert sent(client) == []

    def test_denies_unlisted_prefix(self, client):
        result = server.send_raw_osc("/etc/passwd")
        assert "not under an allowed prefix" in result
        assert sent(client) == []

    def test_allows_snapshot_paths_on_xair(self, client):
        assert "Sent OSC" in server.send_raw_osc("/-snap/load", [1])

    def test_allowlist_is_per_model(self):
        """WING namespaces are refused on X-Air and allowed on WING."""
        xair = connect_as("XR18")
        assert "Refused" in server.send_raw_osc("/$ctl/lib/foo")
        assert sent(xair) == []

        wing = connect_as("WING")
        assert "Sent OSC" in server.send_raw_osc("/$ctl/lib/foo")
        assert sent(wing) == [("/$ctl/lib/foo",)]

    def test_xair_snapshot_path_refused_on_wing(self):
        mock = connect_as("WING")
        assert "Refused" in server.send_raw_osc("/-snap/load", [1])
        assert sent(mock) == []

    def test_wing_hash_form_denied(self):
        mock = connect_as("WING")
        assert "Refused" in server.send_raw_osc("/#f50f69f8", [1])
        assert sent(mock) == []

    def test_wing_network_reconfig_denied(self):
        mock = connect_as("WING")
        assert "Refused" in server.send_raw_osc("/cfg/net/ip", ["10.0.0.1"])
        assert sent(mock) == []

    def test_osc_get_reads(self, client):
        client.query.return_value = [0.75]
        assert server.osc_get("/ch/01/mix/fader")["value"] == [0.75]

    def test_osc_get_is_gated(self, client):
        assert "error" in server.osc_get("/node")

    def test_osc_get_timeout(self, client):
        client.query.return_value = None
        assert "error" in server.osc_get("/ch/01/mix/fader")

    def test_osc_get_many(self, client):
        client.query_many.return_value = {
            "/ch/01/mix/fader": [0.75],
            "/ch/02/mix/fader": None,
        }
        result = server.osc_get_many(["/ch/01/mix/fader", "/ch/02/mix/fader"])
        assert result["values"] == {"/ch/01/mix/fader": [0.75]}
        assert result["timed_out"] == ["/ch/02/mix/fader"]

    def test_osc_get_many_gated(self, client):
        assert "error" in server.osc_get_many(["/ch/01/mix/fader", "/node"])


# ---------------------------------------------------------------------------
# Read-only mode
# ---------------------------------------------------------------------------


class TestReadOnly:
    @pytest.fixture(autouse=True)
    def enable(self, monkeypatch):
        monkeypatch.setenv("OSC_MCP_READ_ONLY", "1")

    @pytest.mark.parametrize(
        "call",
        [
            lambda: server.set_channel_fader(1, -10),
            lambda: server.set_channel_mute(1, True),
            lambda: server.set_channel_pan(1, 0),
            lambda: server.set_channel_gain(1, 20),
            lambda: server.set_phantom_power(1, True),
            lambda: server.set_bus_fader(1, -10),
            lambda: server.set_bus_mute(1, True),
            lambda: server.set_channel_send_to_bus(1, 1, -10),
            lambda: server.set_main_fader(-10),
            lambda: server.set_main_mute(True),
            lambda: server.set_dca_fader(1, -10),
            lambda: server.set_dca_mute(1, True),
            lambda: server.set_channel_eq(1, 1, 1000, 0, 2),
            lambda: server.set_channel_eq_on(1, True),
            lambda: server.set_fx_send_fader(1, -10),
            lambda: server.set_fx_send_mute(1, True),
            lambda: server.recall_scene(1),
            lambda: server.send_raw_osc("/ch/01/mix/fader", [0.5]),
            lambda: server.batch([{"op": "main_mute", "muted": True}]),
        ],
    )
    def test_writes_are_refused(self, client, call):
        assert call() == server.READ_ONLY_MESSAGE
        assert sent(client) == []

    def test_reads_still_work(self, client):
        client.query.return_value = [0.75]
        assert "0.0 dB" in server.get_channel_fader(1)

    def test_osc_get_still_works(self, client):
        client.query.return_value = [1]
        assert server.osc_get("/ch/01/mix/on")["value"] == [1]

    def test_strip_status_still_works(self, client):
        client.query_many.return_value = {}
        assert server.get_strip_status(1)["channel"] == 1

    def test_is_read_only_accepts_truthy_values(self, monkeypatch):
        for value in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("OSC_MCP_READ_ONLY", value)
            assert config.is_read_only() is True
        for value in ("0", "false", "", "no"):
            monkeypatch.setenv("OSC_MCP_READ_ONLY", value)
            assert config.is_read_only() is False


# ---------------------------------------------------------------------------
# Names and info
# ---------------------------------------------------------------------------


class TestNamesAndInfo:
    def test_assign_and_list(self, client):
        server.assign_channel_name(1, "Kick")
        server.assign_bus_name(2, "Drummer")
        names = server.list_names()
        assert names["channels"] == {1: "Kick"}
        assert names["buses"] == {2: "Drummer"}
        assert names["dcas"] == {}

    def test_assign_validates_against_the_model(self, client):
        with pytest.raises(ValueError, match="1-16"):
            server.assign_channel_name(17, "Ghost")

    def test_assign_bus_validates(self, client):
        with pytest.raises(ValueError, match="1-6"):
            server.assign_bus_name(7, "Ghost")

    def test_duplicate_name_rejected(self, client):
        server.assign_channel_name(1, "Kick")
        with pytest.raises(ValueError, match="already assigned"):
            server.assign_channel_name(2, "Kick")

    def test_find_strip(self, client):
        server.assign_channel_name(1, "Kick In")
        server.assign_channel_name(2, "Lead Vox")
        found = server.find_strip("kick")
        assert found["channel"] == [{"number": 1, "name": "Kick In"}]
        assert found["bus"] == []

    def test_get_mixer_info_reports_capabilities(self, client):
        client.query.return_value = ["192.168.1.50", "XR18-4C-D9", "XR18", "1.17"]
        client.ip, client.port = "192.168.1.50", 10024
        info = server.get_mixer_info()
        assert info["model"] == "XR18"
        assert info["channels"] == 16
        assert info["buses"] == 6
        assert info["firmware"] == "1.17"
        assert info["read_only"] is False

    def test_get_mixer_info_surfaces_wing_caveats(self):
        mock = connect_as("WING")
        mock.query.return_value = ["WING", "3.0.6"]
        mock.ip, mock.port = "192.168.1.60", 2223
        info = server.get_mixer_info()
        assert info["model"] == "WING"
        assert info["channels"] == 40
        assert "caveats" in info

    def test_get_mixer_info_survives_timeout(self, client):
        client.query.return_value = None
        client.ip, client.port = "192.168.1.50", 10024
        assert server.get_mixer_info()["model"] == "XR18"

    def test_get_mixer_info_reports_read_only(self, client, monkeypatch):
        monkeypatch.setenv("OSC_MCP_READ_ONLY", "1")
        client.query.return_value = []
        client.ip, client.port = "192.168.1.50", 10024
        assert server.get_mixer_info()["read_only"] is True


# ---------------------------------------------------------------------------
# Metering
# ---------------------------------------------------------------------------


class TestMetering:
    def test_rta_unsupported_on_wing(self):
        connect_as("WING")
        assert "not mapped for WING" in server.capture_rta(2)["error"]

    def test_meters_unsupported_on_wing(self):
        connect_as("WING")
        assert "error" in server.get_meters(0, 0.2)

    def test_rta_reports_when_nothing_arrives(self, client):
        result = server.capture_rta(2)
        assert result["frames"] == 0
        assert "no RTA frames" in result["error"]

    def test_rta_subscribes_and_unsubscribes(self, client):
        server.capture_rta(2)
        assert ("/meters", "/meters/4") in sent(client)
        client.add_meter_handler.assert_called_once()
        client.remove_meter_handler.assert_called_once_with("/meters/4")

    def test_rta_averages_delivered_frames(self, client):
        def deliver(address, handler):
            handler([b"\x00\x00\x00\x00"])  # empty payload, ignored
            handler([_blob([-30.0] * 100)])

        client.add_meter_handler.side_effect = deliver
        result = server.capture_rta(2)
        assert result["frames"] == 1
        assert len(result["spectrum"]) == 100
        assert result["spectrum"][0]["db"] == -30.0
        assert result["spectrum"][0]["hz"] == pytest.approx(20.0)

    def test_get_meters_reports_peaks(self, client):
        def deliver(address, handler):
            handler([_blob([-20.0, -40.0])])
            handler([_blob([-30.0, -10.0])])

        client.add_meter_handler.side_effect = deliver
        result = server.get_meters(0, 0.2)
        assert result["frames"] == 2
        assert result["peak_db"] == [-20.0, -10.0]

    def test_get_meters_with_no_data(self, client):
        assert "error" in server.get_meters(0, 0.2)

    def test_rta_window_is_clamped(self, client):
        assert server.capture_rta(0.1)  # clamped up to the 2 s floor, no hang
