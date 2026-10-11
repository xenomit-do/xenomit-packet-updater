"""Load bindings.toml: const / site → ActionScript class name."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Bindings:
    # modules.rs id::* const → class name
    packet_ids: dict[str, str] = field(default_factory=dict)
    # model.rs comment class name → class name (identity map, keys are class names)
    model_classes: dict[str, str] = field(default_factory=dict)
    # "file.rs:CONST" → class name
    raylib: dict[str, str] = field(default_factory=dict)
    # server live catalog class names (key == value normally)
    server_live: dict[str, str] = field(default_factory=dict)

    def all_class_names(self) -> set[str]:
        names: set[str] = set()
        names.update(self.packet_ids.values())
        names.update(self.model_classes.values())
        names.update(self.raylib.values())
        names.update(self.server_live.values())
        return names


def load_bindings(path: Path) -> Bindings:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    pc = data.get("packet_client", {})
    return Bindings(
        packet_ids=dict(pc.get("id") or {}),
        model_classes=dict(pc.get("model") or {}),
        raylib=dict(data.get("raylib") or {}),
        server_live=dict(data.get("server", {}).get("live") or {}),
    )
