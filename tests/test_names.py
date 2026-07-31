"""Tests for the model-agnostic NameRegistry."""

import pytest

from osc_mcp.names import NameRegistry


class TestNameRegistry:
    def test_assign_and_resolve_by_name(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        assert reg.resolve("channel", "Kick") == 1

    def test_resolve_by_number_int(self):
        reg = NameRegistry()
        assert reg.resolve("channel", 5) == 5

    def test_resolve_by_number_string(self):
        reg = NameRegistry()
        assert reg.resolve("channel", "5") == 5

    def test_case_insensitive_lookup(self):
        reg = NameRegistry()
        reg.assign_name("bus", 2, "Drummer")
        assert reg.resolve("bus", "drummer") == 2
        assert reg.resolve("bus", "DRUMMER") == 2

    def test_duplicate_name_error(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        with pytest.raises(ValueError, match="already assigned"):
            reg.assign_name("channel", 2, "Kick")

    def test_reassign_same_number(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        reg.assign_name("channel", 1, "BassDrum")
        assert reg.resolve("channel", "BassDrum") == 1
        with pytest.raises(ValueError):
            reg.resolve("channel", "Kick")

    def test_unknown_name_error(self):
        reg = NameRegistry()
        with pytest.raises(ValueError, match="Unknown channel name"):
            reg.resolve("channel", "NonExistent")

    def test_list_names(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        reg.assign_name("channel", 3, "Snare")
        assert reg.list_names("channel") == {1: "Kick", 3: "Snare"}

    def test_list_names_empty(self):
        reg = NameRegistry()
        assert reg.list_names("bus") == {}

    def test_invalid_kind(self):
        reg = NameRegistry()
        with pytest.raises(ValueError, match="Kind must be"):
            reg.assign_name("fx", 1, "Reverb")

    def test_dca_is_a_valid_kind(self):
        reg = NameRegistry()
        reg.assign_name("dca", 1, "Band")
        assert reg.resolve("dca", "Band") == 1

    def test_same_name_across_kinds_is_allowed(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Vox")
        reg.assign_name("bus", 1, "Vox")
        assert reg.resolve("channel", "Vox") == 1
        assert reg.resolve("bus", "Vox") == 1

    def test_clear(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        reg.assign_name("dca", 2, "Band")
        reg.clear()
        assert reg.list_names("channel") == {}
        assert reg.list_names("dca") == {}


class TestFind:
    @pytest.fixture
    def reg(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick In")
        reg.assign_name("channel", 2, "Kick Out")
        reg.assign_name("channel", 3, "Lead Vox")
        return reg

    def test_substring_match(self, reg):
        assert [n for n, _ in reg.find("channel", "kick")] == [1, 2]

    def test_exact_match_ranks_first(self, reg):
        reg.assign_name("channel", 4, "Kick")
        assert reg.find("channel", "Kick")[0][0] == 4

    def test_case_insensitive(self, reg):
        assert reg.find("channel", "VOX") == [(3, "Lead Vox")]

    def test_no_match(self, reg):
        assert reg.find("channel", "Tuba") == []
