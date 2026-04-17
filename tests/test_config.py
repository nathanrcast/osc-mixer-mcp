"""Tests for persistent config save/load."""

import json

import pytest

from osc_mcp import config


@pytest.fixture(autouse=True)
def use_tmp_config(tmp_path, monkeypatch):
    """Redirect config to a temp directory for every test."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")


class TestConfig:
    def test_save_load_round_trip(self):
        config.save_mixer_address("192.168.0.2", 10024)
        result = config.load_mixer_address()
        assert result == ("192.168.0.2", 10024)

    def test_load_no_file(self):
        assert config.load_mixer_address() is None

    def test_load_corrupted_json(self):
        config.CONFIG_FILE.write_text("not valid json{{{")
        assert config.load_mixer_address() is None

    def test_load_missing_key(self):
        config.CONFIG_FILE.write_text(json.dumps({"ip": "1.2.3.4"}))
        assert config.load_mixer_address() is None

    def test_save_overwrites(self):
        config.save_mixer_address("192.168.1.10", 10024)
        config.save_mixer_address("192.168.1.11", 10025)
        assert config.load_mixer_address() == ("192.168.1.11", 10025)


class TestIsAllowedIp:
    def test_default_vlan_ip_allowed(self):
        assert config.is_allowed_ip("192.168.1.50") is True

    def test_loopback_allowed(self):
        assert config.is_allowed_ip("127.0.0.1") is True

    def test_other_rfc1918_rejected(self):
        assert config.is_allowed_ip("10.0.0.1") is False
        assert config.is_allowed_ip("172.16.0.1") is False
        assert config.is_allowed_ip("192.168.2.1") is False

    def test_public_ip_rejected(self):
        assert config.is_allowed_ip("8.8.8.8") is False

    def test_malformed_rejected(self):
        assert config.is_allowed_ip("not-an-ip") is False
        assert config.is_allowed_ip("") is False
        assert config.is_allowed_ip("192.168.1.500") is False
