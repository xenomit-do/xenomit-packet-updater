"""Invoke FFDec to export ActionScript and run packet-client extractors."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class DecompileError(RuntimeError):
    pass


def find_module_root(export_dir: Path) -> Path:
    """Locate com/module under an FFDec export tree."""
    direct = (
        export_dir
        / "scripts"
        / "net"
        / "bigpoint"
        / "darkorbit"
        / "com"
        / "module"
    )
    if direct.is_dir():
        return direct
    matches = list(export_dir.rglob("com/module"))
    # Also match Windows path separators via name walk
    if not matches:
        for p in export_dir.rglob("module"):
            if p.is_dir() and p.parent.name == "com":
                matches.append(p)
    if not matches:
        raise DecompileError(
            f"no com/module tree under {export_dir}"
        )
    # Prefer the darkorbit path when several exist
    for m in matches:
        if "darkorbit" in m.parts:
            return m
    return matches[0]


def run_ffdec(ffdec: Path | str, swf: Path, out_dir: Path) -> Path:
    """Export AS3 scripts with FFDec CLI. Returns the com/module directory."""
    ffdec_path = Path(ffdec)
    out_dir.mkdir(parents=True, exist_ok=True)
    # FFDec: ffdec.sh -export script <outdir> <file.swf>
    cmd = [str(ffdec_path), "-export", "script", str(out_dir), str(swf)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise DecompileError(f"ffdec not found: {ffdec_path}") from e
    if proc.returncode != 0:
        raise DecompileError(
            f"ffdec failed ({proc.returncode}): {proc.stderr or proc.stdout}"
        )
    return find_module_root(out_dir)


def run_extract(packet_client: Path, module_root: Path, out_json: Path) -> None:
    script = packet_client / "tools" / "extract_modules.py"
    if not script.is_file():
        raise DecompileError(f"missing extractor: {script}")
    cmd = [
        sys.executable,
        str(script),
        "--root",
        str(module_root),
        "--out",
        str(out_json),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise DecompileError(
            f"extract_modules failed: {proc.stderr or proc.stdout}"
        )


def run_gen_schema(packet_client: Path) -> None:
    script = packet_client / "tools" / "gen_schema_rs.py"
    if not script.is_file():
        raise DecompileError(f"missing gen_schema_rs.py: {script}")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(packet_client),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise DecompileError(
            f"gen_schema_rs failed: {proc.stderr or proc.stdout}"
        )


def copy_modules_json(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
