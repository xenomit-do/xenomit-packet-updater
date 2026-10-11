# xenomit-packet-updater

Detect a new DarkOrbit `main.swf`, regenerate live packet schemas, and rewrite
numeric module IDs (keyed by ActionScript class name) across:

- [`xenomit-packet-client`](../xenomit-packet-client) — `modules.json`,
  `schema.rs`, `modules.rs` `id::*`, `VERSION_HASH`, commented IDs in `model.rs`
- [`xenomit-raylib-client`](../xenomit-raylib-client) — local `i16` consts under
  `src/net/`
- [`xenomit-server`](../xenomit-server) — generated **live** catalog
  (`pkg/protocol/live/catalog.go`, `spec/live-commands.yaml`)

The private-server **v10** catalog (`pkg/protocol/v10`, u16 framing) is left
alone. Live Bigpoint traffic uses u24 framing and a different ID table.

This tool does **not** commit, push, or deploy. A pod can download the SWF,
run `apply`, read `upgrade.json` + the exit code, then orchestrate rebuild and
rollout elsewhere. Memory-offset updates are a separate job; see
[docs/OFFSETS.md](docs/OFFSETS.md).

## Install

```powershell
cd xenomit-packet-updater
python -m pip install -e ".[dev]"
```

## CLI

```powershell
# Exit 0 = same as baseline, 10 = SWF or VERSION_HASH changed
xenomit-packet-updater detect --swf path\to\main.swf

# CronJob-friendly: also write the detect payload to a file
xenomit-packet-updater detect --swf path\to\main.swf --out detect.json

# Full update (needs FFDec CLI, or a pre-exported tree / modules.json)
xenomit-packet-updater apply --swf path\to\main.swf --ffdec path\to\ffdec.bat

# Dry-run for CronJob/Job flows: same exit contract + manifest, writes nothing
xenomit-packet-updater apply --swf path\to\main.swf --modules-json path\to\modules.json --check-only --out upgrade.json

# Offline / CI: feed an already-built modules.json
xenomit-packet-updater apply --swf path\to\main.swf --modules-json path\to\modules.json --out upgrade.json
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Unchanged (`exit_class: none`) |
| 10 | ID / hash update applied; safe to rebuild and roll (`ids`) |
| 30 | Bound class wire shape changed; files updated, review builders/handlers before roll (`review`) |
| 1 | Tool failure (missing FFDec, bound class gone, extract/gen error) |

`apply --check-only` returns the same exit codes and the same manifest but
writes nothing to the checkout: `files_written` stays empty and the would-be
paths are reported as `files_planned`. A missing rewrite target fails with
exit 1 exactly like a real run. A detect/apply Job can therefore classify
`ids` vs `review` and build the PR body before mutating anything.

### `upgrade.json`

```json
{
  "kind": "packet",
  "previous": { "swf_sha256": "...", "version_hash": "..." },
  "next": { "swf_sha256": "...", "version_hash": "..." },
  "id_remaps": [],
  "added": [],
  "removed": [],
  "shape_changes": [],
  "files_written": [],
  "files_planned": [],
  "check_only": false,
  "exit_class": "ids"
}
```

## Bindings

[`bindings.toml`](bindings.toml) maps Rust consts / raylib sites / server live
names to AS3 class names. Seeded from today's `modules.json` IDs. Only those
integers are rewritten; non-module constants (e.g. `REPAIR_TYPE_BASIC`) stay
out of the file.

## Pipeline

```
main.swf → FFDec export → com/module/*.as
  → extract_modules.py --root … --out modules.json
  → gen_schema_rs.py → schema.rs
  → rewrite modules.rs / model.rs / raylib net consts
  → generate server live catalog
  → upgrade.json
```

Fetching the SWF (backpage flashvars → CDN `main.swf?__cv=…`) stays outside
this process; pass `--swf` or `--swf-url` once you have a URL.

## Tests

```powershell
python -m pytest
```

Fixtures only — no network, no FFDec, no live SWF.
