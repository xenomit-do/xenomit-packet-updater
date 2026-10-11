"""CLI entry: xenomit-packet-updater detect|apply."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import EXIT_IDS, EXIT_OK, EXIT_TOOL, __version__
from .apply import ApplyConfig, apply_update, write_manifest
from .detect import changed, identify_swf, load_baseline
from .paths import (
    DEFAULT_BASELINE,
    DEFAULT_BINDINGS,
    DEFAULT_PACKET_CLIENT,
    DEFAULT_RAYLIB,
    DEFAULT_SERVER,
)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--swf",
        type=Path,
        help="Path to main.swf",
    )
    p.add_argument(
        "--swf-url",
        help="Optional HTTPS URL to download main.swf before processing",
    )
    p.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help=f"baseline.json (default: {DEFAULT_BASELINE})",
    )
    p.add_argument(
        "--bindings",
        type=Path,
        default=DEFAULT_BINDINGS,
        help=f"bindings.toml (default: {DEFAULT_BINDINGS})",
    )
    p.add_argument(
        "--packet-client",
        type=Path,
        default=DEFAULT_PACKET_CLIENT,
    )
    p.add_argument(
        "--raylib",
        type=Path,
        default=DEFAULT_RAYLIB,
    )
    p.add_argument(
        "--server",
        type=Path,
        default=DEFAULT_SERVER,
    )


def cmd_detect(args: argparse.Namespace) -> int:
    if args.swf_url and not args.swf:
        args.swf = Path("main.swf")
        from .apply import fetch_swf

        fetch_swf(args.swf_url, args.swf)
    if not args.swf or not Path(args.swf).is_file():
        print("error: --swf required", file=sys.stderr)
        return EXIT_TOOL
    baseline = load_baseline(args.baseline)
    identity = identify_swf(Path(args.swf))
    payload = {
        "swf_sha256": identity.swf_sha256,
        "version_hash": identity.version_hash,
        "baseline": {
            "swf_sha256": baseline.swf_sha256,
            "version_hash": baseline.version_hash,
        },
        "changed": changed(baseline, identity),
    }
    text = json.dumps(payload, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if identity.version_hash is None:
        print("warning: VERSION_HASH not found in SWF", file=sys.stderr)
    return EXIT_IDS if payload["changed"] else EXIT_OK


def cmd_apply(args: argparse.Namespace) -> int:
    if not args.swf and not args.swf_url and not args.modules_json:
        print(
            "error: need --swf, --swf-url, or --modules-json",
            file=sys.stderr,
        )
        return EXIT_TOOL
    swf = Path(args.swf) if args.swf else Path("main.swf")
    cfg = ApplyConfig(
        swf=swf,
        baseline=args.baseline,
        bindings=args.bindings,
        packet_client=args.packet_client,
        raylib=args.raylib,
        server=args.server,
        ffdec=Path(args.ffdec) if args.ffdec else None,
        out_manifest=args.out,
        module_root=Path(args.module_root) if args.module_root else None,
        modules_json=Path(args.modules_json) if args.modules_json else None,
        work_dir=Path(args.work_dir) if args.work_dir else None,
        update_baseline=args.update_baseline,
        swf_url=args.swf_url,
        check_only=args.check_only,
    )
    result = apply_update(cfg)
    out = args.out or Path("upgrade.json")
    write_manifest(out, result)
    print(json.dumps(result.to_manifest(), indent=2))
    if result.error:
        print(f"error: {result.error}", file=sys.stderr)
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xenomit-packet-updater",
        description=(
            "Detect DarkOrbit client updates and realign packet schemas "
            "in xenomit-packet-client, xenomit-raylib-client, and "
            "xenomit-server (live catalog)."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    detect_p = sub.add_parser(
        "detect",
        help="Compare SWF hash + VERSION_HASH against baseline (exit 10 if changed)",
    )
    _add_common(detect_p)
    detect_p.add_argument(
        "--out",
        type=Path,
        help="Also write the detect JSON payload to this path",
    )
    detect_p.set_defaults(func=cmd_detect)

    apply_p = sub.add_parser(
        "apply",
        help="Decompile, regenerate schemas, rewrite IDs, emit upgrade.json",
    )
    _add_common(apply_p)
    apply_p.add_argument(
        "--ffdec",
        help="Path to ffdec / ffdec.sh / ffdec.bat CLI",
    )
    apply_p.add_argument(
        "--module-root",
        help="Skip FFDec; path to already-exported com/module tree",
    )
    apply_p.add_argument(
        "--modules-json",
        help="Skip decompile+extract; use this modules.json directly",
    )
    apply_p.add_argument(
        "--out",
        type=Path,
        default=Path("upgrade.json"),
        help="upgrade.json path (default: ./upgrade.json)",
    )
    apply_p.add_argument(
        "--work-dir",
        type=Path,
        help="Scratch directory (default: system temp)",
    )
    apply_p.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite baseline.json to the new SWF identity after success",
    )
    apply_p.add_argument(
        "--check-only",
        action="store_true",
        help=(
            "Decompile + diff + manifest + exit code, but write nothing. "
            "Planned writes are listed as files_planned in upgrade.json "
            "(CronJob/Job dry-run contract)."
        ),
    )
    apply_p.set_defaults(func=cmd_apply)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
