import json
from pathlib import Path

from xenomit_packet_updater import EXIT_IDS, cli
from xenomit_packet_updater.detect import (
    Baseline,
    SwfIdentity,
    changed,
    extract_version_hash,
    identify_swf,
)


def test_extract_version_hash_adjacent():
    # Mimic ABC string pool: name then length byte then 32 hex chars
    data = b"xxxxVERSION_HASH " + b"43e9184871f4b91cc4158e5c5bef3d3f" + b"yyyy"
    assert extract_version_hash(data) == "43e9184871f4b91cc4158e5c5bef3d3f"


def test_extract_version_hash_missing():
    assert extract_version_hash(b"no hash here") is None


def test_identify_uncompressed_swf(tmp_path: Path):
    body = b"FWS\x0a\x00\x00\x00" + b"padVERSION_HASH\x20" + (
        b"bd171f00112233445566778899aabbcc"
    )
    swf = tmp_path / "main.swf"
    swf.write_bytes(body)
    ident = identify_swf(swf)
    assert ident.version_hash == "bd171f00112233445566778899aabbcc"
    assert len(ident.swf_sha256) == 64


def test_changed_on_hash_or_version():
    base = Baseline(
        swf_sha256="AA" * 32,
        version_hash="43e9184871f4b91cc4158e5c5bef3d3f",
    )
    same = SwfIdentity(
        swf_sha256="aa" * 32,
        version_hash="43e9184871f4b91cc4158e5c5bef3d3f",
    )
    assert not changed(base, same)
    assert changed(
        base,
        SwfIdentity(swf_sha256="BB" * 32, version_hash=same.version_hash),
    )
    assert changed(
        base,
        SwfIdentity(
            swf_sha256=same.swf_sha256,
            version_hash="bd171f00112233445566778899aabbcc",
        ),
    )


def test_cmd_detect_out_writes_payload(tmp_path: Path):
    swf = tmp_path / "main.swf"
    swf.write_bytes(
        b"FWS\x0a\x00\x00\x00VERSION_HASH "
        + b"bd171f00112233445566778899aabbcc"
    )
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
    out = tmp_path / "out" / "detect.json"
    rc = cli.main(
        [
            "detect",
            "--swf",
            str(swf),
            "--baseline",
            str(baseline),
            "--out",
            str(out),
        ]
    )
    assert rc == EXIT_IDS
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["changed"] is True
    assert payload["swf_sha256"] == identify_swf(swf).swf_sha256
    assert payload["version_hash"] == "bd171f00112233445566778899aabbcc"
