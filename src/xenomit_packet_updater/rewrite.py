"""Rewrite numeric module IDs and VERSION_HASH in Rust sources by class name."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .bindings import Bindings
from .catalog import Module


@dataclass
class RewriteResult:
    files_written: list[str] = field(default_factory=list)
    remaps: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


_CONST_RE = re.compile(
    r"(pub(?:\(crate\))?\s+const\s+|const\s+)([A-Z][A-Z0-9_]*)\s*:\s*i16\s*=\s*(-?\d+)\s*;"
)
_VERSION_HASH_RE = re.compile(
    r'(pub\s+const\s+VERSION_HASH\s*:\s*&str\s*=\s*")([0-9a-fA-F]{32})("\s*;)'
)
# `3245 /* AssetRemoveCommand */` or `-6137 /* RemoveCollectableCommand */`
_COMMENTED_ID_RE = re.compile(r"(-?\d+)\s*/\*\s*([A-Za-z_][A-Za-z0-9_]*)\s*\*/")


def rewrite_modules_rs(
    path: Path,
    bindings: Bindings,
    catalog: dict[str, Module],
    version_hash: str | None,
) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    remaps: list[dict] = []

    def replace_const(m: re.Match[str]) -> str:
        prefix, name, old_s = m.group(1), m.group(2), m.group(3)
        class_name = bindings.packet_ids.get(name)
        if class_name is None:
            return m.group(0)
        mod = catalog.get(class_name)
        if mod is None or mod.module_id is None:
            remaps.append(
                {
                    "file": str(path),
                    "const": name,
                    "class": class_name,
                    "error": "missing",
                }
            )
            return m.group(0)
        old = int(old_s)
        new = int(mod.module_id)
        if old != new:
            remaps.append(
                {
                    "file": str(path),
                    "const": name,
                    "class": class_name,
                    "old_id": old,
                    "new_id": new,
                }
            )
        return f"{prefix}{name}: i16 = {new};"

    text = _CONST_RE.sub(replace_const, text)

    if version_hash:
        def replace_hash(m: re.Match[str]) -> str:
            old = m.group(2)
            if old.lower() != version_hash.lower():
                remaps.append(
                    {
                        "file": str(path),
                        "const": "VERSION_HASH",
                        "old": old,
                        "new": version_hash.lower(),
                    }
                )
            return f"{m.group(1)}{version_hash.lower()}{m.group(3)}"

        text = _VERSION_HASH_RE.sub(replace_hash, text)

    path.write_text(text, encoding="utf-8")
    return remaps


def rewrite_model_rs(
    path: Path,
    bindings: Bindings,
    catalog: dict[str, Module],
) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    remaps: list[dict] = []
    class_set = set(bindings.model_classes.values()) | set(
        bindings.model_classes.keys()
    )

    def replace(m: re.Match[str]) -> str:
        old_s, class_name = m.group(1), m.group(2)
        if class_name not in class_set:
            return m.group(0)
        mod = catalog.get(class_name)
        if mod is None or mod.module_id is None:
            remaps.append(
                {
                    "file": str(path),
                    "class": class_name,
                    "error": "missing",
                }
            )
            return m.group(0)
        old = int(old_s)
        new = int(mod.module_id)
        if old != new:
            remaps.append(
                {
                    "file": str(path),
                    "class": class_name,
                    "old_id": old,
                    "new_id": new,
                }
            )
        return f"{new} /* {class_name} */"

    text = _COMMENTED_ID_RE.sub(replace, text)
    path.write_text(text, encoding="utf-8")
    return remaps


def rewrite_raylib_file(
    path: Path,
    const_to_class: dict[str, str],
    catalog: dict[str, Module],
) -> list[dict]:
    """Rewrite i16 consts in one raylib net/*.rs file."""
    text = path.read_text(encoding="utf-8")
    remaps: list[dict] = []

    def replace_const(m: re.Match[str]) -> str:
        prefix, name, old_s = m.group(1), m.group(2), m.group(3)
        class_name = const_to_class.get(name)
        if class_name is None:
            return m.group(0)
        mod = catalog.get(class_name)
        if mod is None or mod.module_id is None:
            remaps.append(
                {
                    "file": str(path),
                    "const": name,
                    "class": class_name,
                    "error": "missing",
                }
            )
            return m.group(0)
        old = int(old_s)
        new = int(mod.module_id)
        if old != new:
            remaps.append(
                {
                    "file": str(path),
                    "const": name,
                    "class": class_name,
                    "old_id": old,
                    "new_id": new,
                }
            )
        return f"{prefix}{name}: i16 = {new};"

    text = _CONST_RE.sub(replace_const, text)
    path.write_text(text, encoding="utf-8")
    return remaps


def apply_rust_rewrites(
    packet_client: Path,
    raylib: Path,
    bindings: Bindings,
    catalog: dict[str, Module],
    version_hash: str | None,
) -> RewriteResult:
    result = RewriteResult()
    modules_rs = packet_client / "src" / "modules.rs"
    model_rs = packet_client / "src" / "model.rs"

    remaps = rewrite_modules_rs(modules_rs, bindings, catalog, version_hash)
    result.files_written.append(str(modules_rs))
    result.remaps.extend(remaps)

    remaps = rewrite_model_rs(model_rs, bindings, catalog)
    result.files_written.append(str(model_rs))
    result.remaps.extend(remaps)

    # Group raylib bindings by file
    by_file: dict[str, dict[str, str]] = {}
    for key, class_name in bindings.raylib.items():
        if ":" not in key:
            continue
        file_name, const = key.split(":", 1)
        by_file.setdefault(file_name, {})[const] = class_name

    net = raylib / "src" / "net"
    for file_name, const_map in by_file.items():
        path = net / file_name
        if not path.is_file():
            result.missing.append(str(path))
            continue
        remaps = rewrite_raylib_file(path, const_map, catalog)
        result.files_written.append(str(path))
        result.remaps.extend(remaps)

    for r in result.remaps:
        if r.get("error") == "missing":
            result.missing.append(r.get("class") or r.get("const") or "?")

    # Bound classes absent from catalog
    for class_name in bindings.all_class_names():
        if class_name not in catalog or catalog[class_name].module_id is None:
            if class_name not in result.missing:
                result.missing.append(class_name)

    return result
