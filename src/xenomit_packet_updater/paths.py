"""Default sibling-repo layout under the xenomit workspace."""

from __future__ import annotations

from pathlib import Path

# xenomit-packet-updater/
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
# repos/
WORKSPACE = PACKAGE_ROOT.parent

DEFAULT_PACKET_CLIENT = WORKSPACE / "xenomit-packet-client"
DEFAULT_RAYLIB = WORKSPACE / "xenomit-raylib-client"
DEFAULT_SERVER = WORKSPACE / "xenomit-server"
DEFAULT_GAME_RESOURCES = WORKSPACE / "game_resources"
DEFAULT_BINDINGS = PACKAGE_ROOT / "bindings.toml"
DEFAULT_BASELINE = PACKAGE_ROOT / "baseline.json"

EXTRACT_SCRIPT = "tools/extract_modules.py"
GEN_SCHEMA_SCRIPT = "tools/gen_schema_rs.py"
MODULES_JSON = "tools/modules.json"
SCHEMA_RS = "src/generated/schema.rs"
MODULES_RS = "src/modules.rs"
MODEL_RS = "src/model.rs"
