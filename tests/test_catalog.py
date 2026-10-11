from pathlib import Path

from xenomit_packet_updater.catalog import diff_catalogs, load_catalog

FIXTURES = Path(__file__).parent / "fixtures"


def test_diff_id_remap_and_added_removed():
    old = load_catalog(FIXTURES / "modules_old.json")
    new = load_catalog(FIXTURES / "modules_new.json")
    d = diff_catalogs(old, new)
    assert "BrandNewModule" in d.added
    assert "UnboundExtra" in d.removed
    remaps = {r["name"]: r for r in d.id_remaps}
    assert remaps["MoveRequest"]["old_id"] == 82
    assert remaps["MoveRequest"]["new_id"] == 1800
    assert remaps["AssetRemoveCommand"]["new_id"] == 4001
    shapes = {s.name: s for s in d.shape_changes}
    assert "LoginRequest" in shapes
    assert shapes["LoginRequest"].side == "write"
    assert "MoveRequest" not in shapes
