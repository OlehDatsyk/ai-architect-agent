"""Readable, unique Blender object names: Wall_GroundFloor_Front_01, Room_MasterBedroom."""

import re

FLOOR_WORDS = ["GroundFloor", "FirstFloor", "SecondFloor", "ThirdFloor", "FourthFloor"]


def floor_word(level: int) -> str:
    return FLOOR_WORDS[level] if level < len(FLOOR_WORDS) else f"Floor{level}"


def camel(text: str) -> str:
    """'Master bedroom / study' -> 'MasterBedroomStudy'. Anything outside A-Z, a-z, 0-9 is dropped."""
    words = re.findall(r"[A-Za-z0-9]+", text)
    result = "".join(w[:1].upper() + w[1:] for w in words)
    return result or "Unnamed"


class NameRegistry:
    def __init__(self) -> None:
        self._used: set[str] = set()

    def unique(self, base: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_]", "", base)[:56] or "Object"
        if not base[0].isalpha():
            base = "X" + base
        name, n = base, 1
        while name in self._used:
            n += 1
            name = f"{base}_{n:02d}"
        self._used.add(name)
        return name

    def numbered(self, base: str) -> str:
        """Always numbered: Wall_GroundFloor_Front_01, _02..."""
        n = 1
        while f"{base}_{n:02d}" in self._used:
            n += 1
        return self.unique(f"{base}_{n:02d}")
