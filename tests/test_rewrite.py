import shutil
from pathlib import Path

from xenomit_packet_updater.bindings import load_bindings
from xenomit_packet_updater.catalog import load_catalog
from xenomit_packet_updater.rewrite import (
    apply_rust_rewrites,
    rewrite_model_rs,
    rewrite_modules_rs,
    rewrite_raylib_file,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_rewrite_modules_rs_remaps_and_skips_unbound(tmp_path: Path):
    path = tmp_path / "modules.rs"
    shutil.copy(FIXTURES / "modules_rs_snippet.rs", path)
    bindings = load_bindings(FIXTURES / "bindings_test.toml")
    catalog = load_catalog(FIXTURES / "modules_new.json")
    remaps = rewrite_modules_rs(
        path, bindings, catalog, version_hash="bd171f00112233445566778899aabbcc"
    )
    text = path.read_text(encoding="utf-8")
    assert "MOVE_REQUEST: i16 = 1800;" in text
    assert "LOGIN_REQUEST: i16 = 7;" in text
    assert "UNRELATED: i16 = 42;" in text  # unbound left alone
    assert 'VERSION_HASH: &str = "bd171f00112233445566778899aabbcc";' in text
    by_const = {r["const"]: r for r in remaps if "const" in r}
    assert by_const["MOVE_REQUEST"]["new_id"] == 1800
    assert by_const["VERSION_HASH"]["new"] == "bd171f00112233445566778899aabbcc"


def test_rewrite_model_commented_ids(tmp_path: Path):
    path = tmp_path / "model.rs"
    shutil.copy(FIXTURES / "model_rs_snippet.rs", path)
    bindings = load_bindings(FIXTURES / "bindings_test.toml")
    catalog = load_catalog(FIXTURES / "modules_new.json")
    remaps = rewrite_model_rs(path, bindings, catalog)
    text = path.read_text(encoding="utf-8")
    assert "4001 /* AssetRemoveCommand */" in text
    assert "-6137 /* RemoveCollectableCommand */" in text
    assert remaps[0]["new_id"] == 4001


def test_rewrite_raylib_file(tmp_path: Path):
    path = tmp_path / "ships.rs"
    shutil.copy(FIXTURES / "ships_rs_snippet.rs", path)
    catalog = load_catalog(FIXTURES / "modules_new.json")
    remaps = rewrite_raylib_file(
        path, {"ASSET_REMOVE_COMMAND": "AssetRemoveCommand"}, catalog
    )
    text = path.read_text(encoding="utf-8")
    assert "ASSET_REMOVE_COMMAND: i16 = 4001;" in text
    assert "SHIP_SELECTION: i16 = 50;" in text
    assert remaps[0]["new_id"] == 4001


def test_missing_bound_class_reported(tmp_path: Path):
    packet = tmp_path / "packet"
    raylib = tmp_path / "raylib"
    (packet / "src").mkdir(parents=True)
    (raylib / "src" / "net").mkdir(parents=True)
    shutil.copy(FIXTURES / "modules_rs_snippet.rs", packet / "src" / "modules.rs")
    shutil.copy(FIXTURES / "model_rs_snippet.rs", packet / "src" / "model.rs")
    shutil.copy(FIXTURES / "ships_rs_snippet.rs", raylib / "src" / "net" / "ships.rs")
    bindings = load_bindings(FIXTURES / "bindings_test.toml")
    # Drop MoveRequest from catalog
    catalog = load_catalog(FIXTURES / "modules_new.json")
    del catalog["MoveRequest"]
    result = apply_rust_rewrites(
        packet, raylib, bindings, catalog, version_hash=None
    )
    assert "MoveRequest" in result.missing
