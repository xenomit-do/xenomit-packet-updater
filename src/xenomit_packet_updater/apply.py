"""End-to-end apply: decompile → extract → diff → rewrite → regenerate."""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import EXIT_IDS, EXIT_OK, EXIT_REVIEW, EXIT_TOOL
from .bindings import Bindings, load_bindings
from .catalog import CatalogDiff, Module, diff_catalogs, load_catalog
from .decompile import (
    DecompileError,
    copy_modules_json,
    run_extract,
    run_ffdec,
    run_gen_schema,
)
from .detect import Baseline, SwfIdentity, changed, identify_swf, load_baseline
from .go_gen import write_live_catalog
from .rewrite import apply_rust_rewrites


@dataclass
class ApplyConfig:
    swf: Path
    baseline: Path
    bindings: Path
    packet_client: Path
    raylib: Path
    server: Path
    ffdec: Path | None = None
    out_manifest: Path | None = None
    # Skip FFDec; use an already-exported com/module tree or modules.json
    module_root: Path | None = None
    modules_json: Path | None = None
    work_dir: Path | None = None
    update_baseline: bool = False
    swf_url: str | None = None
    # CronJob/Job dry-run: decompile + diff + manifest + exit code, but write
    # nothing. The would-be-written paths land in files_planned instead.
    check_only: bool = False


@dataclass
class ApplyResult:
    exit_code: int
    identity: SwfIdentity | None = None
    baseline: Baseline | None = None
    diff: CatalogDiff | None = None
    files_written: list[str] = field(default_factory=list)
    # Set only in check-only mode: the paths a real apply would write.
    files_planned: list[str] = field(default_factory=list)
    check_only: bool = False
    remaps: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    bound_shape_changes: list[dict] = field(default_factory=list)
    exit_class: str = "none"
    error: str | None = None

    def to_manifest(self) -> dict[str, Any]:
        prev = None
        if self.baseline is not None:
            prev = {
                "swf_sha256": self.baseline.swf_sha256,
                "version_hash": self.baseline.version_hash,
            }
        nxt = None
        if self.identity is not None:
            nxt = {
                "swf_sha256": self.identity.swf_sha256,
                "version_hash": self.identity.version_hash,
            }
        diff_dict = self.diff.to_dict() if self.diff else {
            "added": [],
            "removed": [],
            "id_remaps": [],
            "shape_changes": [],
        }
        return {
            "kind": "packet",
            "previous": prev,
            "next": nxt,
            "id_remaps": self.remaps or diff_dict.get("id_remaps", []),
            "added": diff_dict.get("added", []),
            "removed": diff_dict.get("removed", []),
            "shape_changes": self.bound_shape_changes
            or diff_dict.get("shape_changes", []),
            "files_written": self.files_written,
            "files_planned": self.files_planned,
            "check_only": self.check_only,
            "missing": self.missing,
            "exit_class": self.exit_class,
            "error": self.error,
        }


def fetch_swf(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)  # noqa: S310 — intentional HTTPS GET
    return dest


def _planned_writes(
    cfg: ApplyConfig, bindings: Bindings
) -> tuple[list[str], list[str]]:
    """Paths a real apply would write, in files_written order, plus any
    raylib rewrite targets that do not exist (they would fail a real run)."""
    planned = [
        str(cfg.packet_client / "tools" / "modules.json"),
        str(cfg.packet_client / "src" / "generated" / "schema.rs"),
        str(cfg.packet_client / "src" / "modules.rs"),
        str(cfg.packet_client / "src" / "model.rs"),
    ]
    missing: list[str] = []
    net = cfg.raylib / "src" / "net"
    seen: set[str] = set()
    for key in bindings.raylib:
        if ":" not in key:
            continue
        file_name = key.split(":", 1)[0]
        if file_name in seen:
            continue
        seen.add(file_name)
        target = net / file_name
        if target.is_file():
            planned.append(str(target))
        else:
            missing.append(str(target))
    planned.extend(
        [
            str(cfg.server / "spec" / "live-commands.yaml"),
            str(cfg.server / "pkg" / "protocol" / "live" / "catalog.go"),
        ]
    )
    return planned, missing


def _bound_shape_changes(
    diff: CatalogDiff, bindings: Bindings
) -> list[dict]:
    names = bindings.all_class_names()
    out = []
    for s in diff.shape_changes:
        if s.name in names:
            out.append(
                {
                    "name": s.name,
                    "old_id": s.old_id,
                    "new_id": s.new_id,
                    "side": s.side,
                    "detail": s.detail,
                    "review": [
                        "xenomit-packet-client/src/modules.rs",
                        "xenomit-raylib-client/src/net/*",
                    ],
                }
            )
    return out


def apply_update(cfg: ApplyConfig) -> ApplyResult:
    result = ApplyResult(exit_code=EXIT_OK)
    result.check_only = cfg.check_only
    try:
        swf = cfg.swf
        if cfg.swf_url:
            swf = cfg.work_dir / "main.swf" if cfg.work_dir else swf
            if cfg.work_dir:
                cfg.work_dir.mkdir(parents=True, exist_ok=True)
            fetch_swf(cfg.swf_url, swf)

        if not swf.is_file():
            result.exit_code = EXIT_TOOL
            result.error = f"swf not found: {swf}"
            result.exit_class = "error"
            return result

        baseline = load_baseline(cfg.baseline)
        identity = identify_swf(swf)
        result.baseline = baseline
        result.identity = identity
        bindings = load_bindings(cfg.bindings)

        old_json = cfg.packet_client / "tools" / "modules.json"
        if not old_json.is_file():
            result.exit_code = EXIT_TOOL
            result.error = f"missing {old_json}"
            result.exit_class = "error"
            return result
        old_catalog = load_catalog(old_json)

        work = cfg.work_dir
        tmp: tempfile.TemporaryDirectory[str] | None = None
        if work is None:
            tmp = tempfile.TemporaryDirectory(prefix="xpu-")
            work = Path(tmp.name)
        work.mkdir(parents=True, exist_ok=True)

        try:
            new_json = work / "modules.json"
            if cfg.modules_json is not None:
                copy_modules_json(cfg.modules_json, new_json)
            else:
                module_root = cfg.module_root
                if module_root is None:
                    if cfg.ffdec is None:
                        result.exit_code = EXIT_TOOL
                        result.error = (
                            "need --ffdec, --module-root, or --modules-json"
                        )
                        result.exit_class = "error"
                        return result
                    export_dir = work / "ffdec"
                    module_root = run_ffdec(cfg.ffdec, swf, export_dir)
                run_extract(cfg.packet_client, module_root, new_json)

            new_catalog = load_catalog(new_json)
            diff = diff_catalogs(old_catalog, new_catalog)
            result.diff = diff

            # Nothing changed vs baseline and catalog identical?
            if not changed(baseline, identity) and not (
                diff.added
                or diff.removed
                or diff.id_remaps
                or diff.shape_changes
            ):
                result.exit_code = EXIT_OK
                result.exit_class = "none"
                return result

            # Missing bound classes → hard fail before writing
            missing = [
                n
                for n in bindings.all_class_names()
                if n not in new_catalog or new_catalog[n].module_id is None
            ]
            if missing:
                result.missing = missing
                result.exit_code = EXIT_TOOL
                result.error = f"bound classes missing: {', '.join(missing)}"
                result.exit_class = "error"
                return result

            bound_shapes = _bound_shape_changes(diff, bindings)
            result.bound_shape_changes = bound_shapes

            if cfg.check_only:
                planned, missing_targets = _planned_writes(cfg, bindings)
                result.files_planned = planned
                if missing_targets:
                    result.missing = missing_targets
                    result.exit_code = EXIT_TOOL
                    result.error = (
                        "rewrite targets missing: "
                        + ", ".join(missing_targets)
                    )
                    result.exit_class = "error"
                    return result
                if cfg.update_baseline and identity.version_hash:
                    result.files_planned.append(str(cfg.baseline))
            else:
                # Install modules.json + regenerate schema.rs
                dest_json = cfg.packet_client / "tools" / "modules.json"
                shutil.copy2(new_json, dest_json)
                result.files_written.append(str(dest_json))
                run_gen_schema(cfg.packet_client)
                schema_rs = (
                    cfg.packet_client / "src" / "generated" / "schema.rs"
                )
                result.files_written.append(str(schema_rs))

                rewrite = apply_rust_rewrites(
                    cfg.packet_client,
                    cfg.raylib,
                    bindings,
                    new_catalog,
                    identity.version_hash,
                )
                result.files_written.extend(rewrite.files_written)
                result.remaps = rewrite.remaps
                if rewrite.missing:
                    result.missing = rewrite.missing
                    result.exit_code = EXIT_TOOL
                    result.error = (
                        f"rewrite missing classes: {', '.join(rewrite.missing)}"
                    )
                    result.exit_class = "error"
                    return result

                go_files = write_live_catalog(
                    cfg.server, new_catalog, bindings.server_live
                )
                result.files_written.extend(go_files)

                if cfg.update_baseline and identity.version_hash:
                    from .detect import save_baseline

                    save_baseline(cfg.baseline, identity, source=str(swf))
                    result.files_written.append(str(cfg.baseline))

            if bound_shapes:
                result.exit_code = EXIT_REVIEW
                result.exit_class = "review"
            elif (
                diff.id_remaps
                or rewrite.remaps
                or changed(baseline, identity)
            ):
                result.exit_code = EXIT_IDS
                result.exit_class = "ids"
            else:
                # catalog noise only (unbound add/remove) — still wrote live cat
                result.exit_code = EXIT_IDS
                result.exit_class = "ids"
            return result
        finally:
            if tmp is not None:
                tmp.cleanup()
    except DecompileError as e:
        result.exit_code = EXIT_TOOL
        result.error = str(e)
        result.exit_class = "error"
        return result
    except Exception as e:  # noqa: BLE001 — CLI boundary
        result.exit_code = EXIT_TOOL
        result.error = f"{type(e).__name__}: {e}"
        result.exit_class = "error"
        return result


def write_manifest(path: Path, result: ApplyResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_manifest(), indent=2) + "\n", encoding="utf-8"
    )
