"""Load modules.json catalogs and diff them by class name."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Module:
    name: str
    module_id: int | None
    read_ops: list[Any] = field(default_factory=list)
    write_ops: list[Any] = field(default_factory=list)
    parent: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Module:
        return cls(
            name=d["name"],
            module_id=d.get("module_id"),
            read_ops=list(d.get("read_ops") or []),
            write_ops=list(d.get("write_ops") or []),
            parent=d.get("parent"),
            raw=d,
        )


def load_catalog(path: Path) -> dict[str, Module]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, Module] = {}
    for entry in data:
        if not isinstance(entry, dict) or "name" not in entry:
            continue
        m = Module.from_dict(entry)
        out[m.name] = m
    return out


def catalog_by_id(catalog: dict[str, Module]) -> dict[int, str]:
    return {
        m.module_id: m.name
        for m in catalog.values()
        if m.module_id is not None
    }


@dataclass
class ShapeChange:
    name: str
    old_id: int | None
    new_id: int | None
    side: str  # "read" | "write" | "both"
    detail: str


@dataclass
class CatalogDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    id_remaps: list[dict[str, Any]] = field(default_factory=list)
    shape_changes: list[ShapeChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "id_remaps": self.id_remaps,
            "shape_changes": [
                {
                    "name": s.name,
                    "old_id": s.old_id,
                    "new_id": s.new_id,
                    "side": s.side,
                    "detail": s.detail,
                }
                for s in self.shape_changes
            ],
        }


def _ops_equal(a: list[Any], b: list[Any]) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def diff_catalogs(
    old: dict[str, Module],
    new: dict[str, Module],
    bound_names: set[str] | None = None,
) -> CatalogDiff:
    """Diff by class name. Shape changes are recorded for every class;
    callers filter by bindings when deciding exit 30."""
    result = CatalogDiff()
    old_names = set(old)
    new_names = set(new)
    result.added = sorted(new_names - old_names)
    result.removed = sorted(old_names - new_names)
    for name in sorted(old_names & new_names):
        a, b = old[name], new[name]
        if a.module_id != b.module_id:
            result.id_remaps.append(
                {
                    "name": name,
                    "old_id": a.module_id,
                    "new_id": b.module_id,
                }
            )
        read_same = _ops_equal(a.read_ops, b.read_ops)
        write_same = _ops_equal(a.write_ops, b.write_ops)
        if not read_same or not write_same:
            if not read_same and not write_same:
                side = "both"
            elif not read_same:
                side = "read"
            else:
                side = "write"
            result.shape_changes.append(
                ShapeChange(
                    name=name,
                    old_id=a.module_id,
                    new_id=b.module_id,
                    side=side,
                    detail=f"{side} ops changed",
                )
            )
    if bound_names is not None:
        # keep full lists; filtering is done at apply time
        _ = bound_names
    return result
