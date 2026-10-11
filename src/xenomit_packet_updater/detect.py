"""SWF content hash and VersionHash scrape (mirrors raylib swf_extract)."""

from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SwfIdentity:
    swf_sha256: str
    version_hash: str | None


@dataclass(frozen=True)
class Baseline:
    swf_sha256: str
    version_hash: str


def load_baseline(path: Path) -> Baseline:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Baseline(
        swf_sha256=str(data["swf_sha256"]).upper(),
        version_hash=str(data["version_hash"]).lower(),
    )


def save_baseline(path: Path, identity: SwfIdentity, source: str = "") -> None:
    payload = {
        "swf_sha256": identity.swf_sha256.upper(),
        "version_hash": (identity.version_hash or "").lower(),
        "source": source,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _zlib_inflate(data: bytes) -> bytes | None:
    try:
        return zlib.decompress(data)
    except zlib.error:
        return None


def _swf_payload(raw: bytes) -> bytes:
    """Return SWF body bytes (decompressed when CWS/ZWS)."""
    if len(raw) < 8:
        return raw
    sig = raw[:3]
    if sig == b"FWS":
        return raw
    if sig == b"CWS":
        body = _zlib_inflate(raw[8:])
        return raw[:8] + body if body is not None else raw
    if sig == b"ZWS":
        # LZMA-compressed SWF; scrape compressed bytes as a fallback.
        return raw
    return raw


def extract_version_hash(data: bytes) -> str | None:
    """Find VERSION_HASH then the next 32-hex string (raylib swf_extract)."""
    needle = b"VERSION_HASH"
    at = 0
    while True:
        off = data.find(needle, at)
        if off < 0:
            return None
        start = off + len(needle)
        end = min(start + 64, len(data))
        region = data[start:end]
        for i in range(len(region)):
            cand = region[i : i + 32]
            if len(cand) < 32:
                break
            if all(
                (48 <= b <= 57) or (97 <= b <= 102) or (65 <= b <= 70) for b in cand
            ):
                return cand.decode("ascii").lower()
        at = start


def identify_swf(path: Path) -> SwfIdentity:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    payload = _swf_payload(raw)
    version = extract_version_hash(payload)
    if version is None and payload is not raw:
        version = extract_version_hash(raw)
    return SwfIdentity(swf_sha256=digest, version_hash=version)


def changed(baseline: Baseline, identity: SwfIdentity) -> bool:
    if identity.swf_sha256.upper() != baseline.swf_sha256.upper():
        return True
    if identity.version_hash is None:
        return True
    return identity.version_hash.lower() != baseline.version_hash.lower()
