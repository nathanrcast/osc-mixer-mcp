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
        config.save_mixer_address("10.0.0.1", 10024)
        config.save_mixer_address("10.0.0.2", 10025)
        assert config.load_mixer_address() == ("10.0.0.2", 10025)
