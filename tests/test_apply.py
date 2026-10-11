import json
import shutil
from pathlib import Path

from xenomit_packet_updater import EXIT_IDS, EXIT_REVIEW, EXIT_TOOL
from xenomit_packet_updater.apply import ApplyConfig, apply_update

FIXTURES = Path(__file__).parent / "fixtures"


def _stub_workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    packet = tmp_path / "xenomit-packet-client"
    raylib = tmp_path / "xenomit-raylib-client"
    server = tmp_path / "xenomit-server"
    (packet / "tools").mkdir(parents=True)
    (packet / "src" / "generated").mkdir(parents=True)
    (raylib / "src" / "net").mkdir(parents=True)
    (server / "spec").mkdir(parents=True)
    (server / "pkg" / "protocol" / "live").mkdir(parents=True)

    shutil.copy(FIXTURES / "modules_old.json", packet / "tools" / "modules.json")
    shutil.copy(FIXTURES / "modules_rs_snippet.rs", packet / "src" / "modules.rs")
    shutil.copy(FIXTURES / "model_rs_snippet.rs", packet / "src" / "model.rs")
    shutil.copy(FIXTURES / "ships_rs_snippet.rs", raylib / "src" / "net" / "ships.rs")

    # Stub gen_schema_rs.py: touch schema.rs
    (packet / "tools" / "gen_schema_rs.py").write_text(
        "from pathlib import Path\n"
        "Path('src/generated/schema.rs').write_text('// generated\\n')\n",
        encoding="utf-8",
    )
    (packet / "src" / "generated" / "schema.rs").write_text("// old\n", encoding="utf-8")

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "swf_sha256": "00" * 32,
                "version_hash": "43e9184871f4b91cc4158e5c5bef3d3f",
            }
        ),
        encoding="utf-8",
    )
    # Minimal FWS with VERSION_HASH so identity differs from baseline
    swf = tmp_path / "main.swf"
    swf.write_bytes(
        b"FWS\x0a\x00\x00\x00VERSION_HASH "
        + b"bd171f00112233445566778899aabbcc"
    )
    return packet, raylib, server, baseline


def test_apply_id_remap_exit_ids(tmp_path: Path):
    packet, raylib, server, baseline = _stub_workspace(tmp_path)
    # modules_new without LoginRequest shape change — use a catalog that
    # only remaps ids. Build from new but restore LoginRequest write_ops.
    new = json.loads((FIXTURES / "modules_new.json").read_text(encoding="utf-8"))
    old = json.loads((FIXTURES / "modules_old.json").read_text(encoding="utf-8"))
    old_login = next(m for m in old if m["name"] == "LoginRequest")
    for m in new:
        if m["name"] == "LoginRequest":
            m["write_ops"] = old_login["write_ops"]
    modules_json = tmp_path / "modules_new_ids_only.json"
    modules_json.write_text(json.dumps(new), encoding="utf-8")

    cfg = ApplyConfig(
        swf=tmp_path / "main.swf",
        baseline=baseline,
        bindings=FIXTURES / "bindings_test.toml",
        packet_client=packet,
        raylib=raylib,
        server=server,
        modules_json=modules_json,
        work_dir=tmp_path / "work",
    )
    result = apply_update(cfg)
    assert result.exit_code == EXIT_IDS
    assert result.exit_class == "ids"
    text = (packet / "src" / "modules.rs").read_text(encoding="utf-8")
    assert "MOVE_REQUEST: i16 = 1800;" in text
    assert "UNRELATED: i16 = 42;" in text
    ships = (raylib / "src" / "net" / "ships.rs").read_text(encoding="utf-8")
    assert "ASSET_REMOVE_COMMAND: i16 = 4001;" in ships
    live = (server / "pkg" / "protocol" / "live" / "catalog.go").read_text(
        encoding="utf-8"
    )
    assert "MoveRequestID" in live and "1800" in live
    assert (server / "spec" / "live-commands.yaml").is_file()


def test_apply_check_only_writes_nothing(tmp_path: Path):
    packet, raylib, server, baseline = _stub_workspace(tmp_path)
    cfg = ApplyConfig(
        swf=tmp_path / "main.swf",
        baseline=baseline,
        bindings=FIXTURES / "bindings_test.toml",
        packet_client=packet,
        raylib=raylib,
        server=server,
        modules_json=FIXTURES / "modules_new.json",
        work_dir=tmp_path / "work",
        check_only=True,
    )
    result = apply_update(cfg)
    # Same exit contract as a real run, but the checkout is untouched.
    assert result.exit_code == EXIT_REVIEW
    assert result.exit_class == "review"
    assert result.check_only is True
    assert result.files_written == []
    assert result.files_planned
    assert str(packet / "src" / "modules.rs") in result.files_planned
    assert (
        str(server / "pkg" / "protocol" / "live" / "catalog.go")
        in result.files_planned
    )
    assert any(s["name"] == "LoginRequest" for s in result.bound_shape_changes)
    # Nothing was rewritten or generated.
    assert "MOVE_REQUEST: i16 = 82;" in (
        packet / "src" / "modules.rs"
    ).read_text(encoding="utf-8")
    assert not (server / "pkg" / "protocol" / "live" / "catalog.go").exists()


def test_apply_check_only_reports_missing_target(tmp_path: Path):
    packet, raylib, server, baseline = _stub_workspace(tmp_path)
    (raylib / "src" / "net" / "ships.rs").unlink()
    cfg = ApplyConfig(
        swf=tmp_path / "main.swf",
        baseline=baseline,
        bindings=FIXTURES / "bindings_test.toml",
        packet_client=packet,
        raylib=raylib,
        server=server,
        modules_json=FIXTURES / "modules_new.json",
        work_dir=tmp_path / "work",
        check_only=True,
    )
    result = apply_update(cfg)
    assert result.exit_code == EXIT_TOOL
    assert result.exit_class == "error"
    assert any("ships.rs" in m for m in result.missing)


def test_apply_shape_change_exit_review(tmp_path: Path):
    packet, raylib, server, baseline = _stub_workspace(tmp_path)
    cfg = ApplyConfig(
        swf=tmp_path / "main.swf",
        baseline=baseline,
        bindings=FIXTURES / "bindings_test.toml",
        packet_client=packet,
        raylib=raylib,
        server=server,
        modules_json=FIXTURES / "modules_new.json",
        work_dir=tmp_path / "work",
    )
    result = apply_update(cfg)
    assert result.exit_code == EXIT_REVIEW
    assert result.exit_class == "review"
    assert any(s["name"] == "LoginRequest" for s in result.bound_shape_changes)


def test_apply_missing_class_fails(tmp_path: Path):
    packet, raylib, server, baseline = _stub_workspace(tmp_path)
    broken = json.loads((FIXTURES / "modules_new.json").read_text(encoding="utf-8"))
    broken = [m for m in broken if m["name"] != "MoveRequest"]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    cfg = ApplyConfig(
        swf=tmp_path / "main.swf",
        baseline=baseline,
        bindings=FIXTURES / "bindings_test.toml",
        packet_client=packet,
        raylib=raylib,
        server=server,
        modules_json=path,
        work_dir=tmp_path / "work",
    )
    result = apply_update(cfg)
    assert result.exit_code == EXIT_TOOL
    assert "MoveRequest" in (result.missing or [])
    # Original modules.rs must be untouched on hard fail
    text = (packet / "src" / "modules.rs").read_text(encoding="utf-8")
    assert "MOVE_REQUEST: i16 = 82;" in text
