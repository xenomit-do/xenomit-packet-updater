from pathlib import Path

from xenomit_packet_updater.bindings import load_bindings
from xenomit_packet_updater.catalog import load_catalog
from xenomit_packet_updater.go_gen import generate_live_go, generate_live_yaml, write_live_catalog

FIXTURES = Path(__file__).parent / "fixtures"


def test_generate_live_go_and_yaml():
    catalog = load_catalog(FIXTURES / "modules_new.json")
    bindings = load_bindings(FIXTURES / "bindings_test.toml")
    go = generate_live_go(catalog, bindings.server_live)
    assert "MoveRequestID" in go and "1800" in go
    assert "LoginRequestID" in go and "= 7" in go
    assert '"MoveRequest": MoveRequestID' in go
    yaml = generate_live_yaml(catalog, bindings.server_live)
    assert "name: MoveRequest" in yaml
    assert "id: 1800" in yaml
    assert "type: opaque" not in yaml or "AssetRemoveCommand" in yaml


def test_write_live_catalog(tmp_path: Path):
    server = tmp_path / "server"
    catalog = load_catalog(FIXTURES / "modules_new.json")
    bindings = load_bindings(FIXTURES / "bindings_test.toml")
    written = write_live_catalog(server, catalog, bindings.server_live)
    assert len(written) == 2
    assert (server / "pkg" / "protocol" / "live" / "catalog.go").is_file()
    assert (server / "spec" / "live-commands.yaml").is_file()
