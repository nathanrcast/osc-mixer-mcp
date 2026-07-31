"""Symbolic name registry for mixer strips. Model-agnostic."""

from __future__ import annotations

KINDS = ("channel", "bus", "dca")


class NameRegistry:
    """Bidirectional mapping of symbolic names to numbers for mixer strips."""

    def __init__(self) -> None:
        self._name_to_number: dict[str, dict[str, int]] = {k: {} for k in KINDS}
        self._number_to_name: dict[str, dict[int, str]] = {k: {} for k in KINDS}

    def _validate_kind(self, kind: str) -> None:
        if kind not in KINDS:
            raise ValueError(
                f"Kind must be one of {', '.join(KINDS)}, got '{kind}'"
            )

    def assign_name(self, kind: str, number: int, name: str) -> None:
        """Assign a symbolic name to a strip number."""
        self._validate_kind(kind)
        key = name.lower()

        # Check if name is already used for a different number
        existing = self._name_to_number[kind].get(key)
        if existing is not None and existing != number:
            raise ValueError(
                f"Name '{name}' is already assigned to {kind} {existing}"
            )

        # Remove old name for this number if it exists
        old_name = self._number_to_name[kind].get(number)
        if old_name is not None:
            del self._name_to_number[kind][old_name.lower()]

        self._name_to_number[kind][key] = number
        self._number_to_name[kind][number] = name

    def resolve(self, kind: str, name_or_number: str | int) -> int:
        """Resolve a name or number to a number.

        Accepts an int, a string that parses as int, or a symbolic name.
        """
        self._validate_kind(kind)

        if isinstance(name_or_number, int):
            return name_or_number

        # Try parsing as integer
        try:
            return int(name_or_number)
        except (ValueError, TypeError):
            pass

        # Look up as name (case-insensitive)
        key = name_or_number.lower()
        number = self._name_to_number[kind].get(key)
        if number is None:
            raise ValueError(
                f"Unknown {kind} name: '{name_or_number}'. "
                f"Use assign_{kind}_name() first or pass a number."
            )
        return number

    def find(self, kind: str, query: str) -> list[tuple[int, str]]:
        """Fuzzy-match strips whose name contains query (case-insensitive).

        Exact matches sort first, then prefix matches, then substring.
        """
        self._validate_kind(kind)
        q = query.lower()
        scored: list[tuple[int, int, str]] = []
        for number, name in self._number_to_name[kind].items():
            lowered = name.lower()
            if lowered == q:
                rank = 0
            elif lowered.startswith(q):
                rank = 1
            elif q in lowered:
                rank = 2
            else:
                continue
            scored.append((rank, number, name))
        scored.sort()
        return [(number, name) for _, number, name in scored]

    def clear(self) -> None:
        """Drop every assignment. Used when switching mixers."""
        for kind in KINDS:
            self._name_to_number[kind].clear()
            self._number_to_name[kind].clear()

    def list_names(self, kind: str) -> dict[int, str]:
        """Return dict of number -> name for the given kind."""
        self._validate_kind(kind)
        return dict(self._number_to_name[kind])
