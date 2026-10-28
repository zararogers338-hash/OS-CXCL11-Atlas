"""Download a GEO series' normalised series-matrix file(s) and platform annotation table(s).

    python py/fetch_geo.py GSE21257 --out data/raw/geo

Writes data/raw/geo/<GSE>/{*_series_matrix.txt.gz, GPLxxxx.annot.txt, manifest.json}.
Only the Python standard library is used so data acquisition works before the
analysis environment is installed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GEO_FTP = "https://ftp.ncbi.nlm.nih.gov/geo"
GPL_TABLE = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gpl}&targ=self&form=text&view=data"
UA = {"User-Agent": "OS-CXCL11-Atlas/0.1 (academic research; python urllib)"}


def stem(acc: str) -> str:
    """GSE21257 -> GSE21nnn ; GSE152048 -> GSE152nnn ; GSE999 -> GSEnnn."""
    prefix, num = re.match(r"([A-Z]+)(\d+)", acc).groups()
    return f"{prefix}{num[:-3]}nnn" if len(num) > 3 else f"{prefix}nnn"


def get(url: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 3)
    raise RuntimeError("unreachable")


def _expected_total(r, have: int) -> int | None:
    rng = r.headers.get("Content-Range")  # "bytes 1048576-14296658/14296659"
    if r.status == 206 and rng and "/" in rng and not rng.endswith("*"):
        return int(rng.rsplit("/", 1)[1])
    length = r.headers.get("Content-Length")
    return int(length) if length is not None and r.status == 200 else None


def _gzip_ok(path: Path) -> bool:
    try:
        with gzip.open(path, "rb") as fh:
            while fh.read(1 << 22):
                pass
        return True
    except (OSError, EOFError):
        return False


def download(url: str, dest: Path, retries: int = 8) -> dict:
    """Stream to <dest>.part with a stall timeout, resume via HTTP Range, and verify the
    final size (Content-Length / Content-Range) and gzip integrity before accepting it."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        have = tmp.stat().st_size if tmp.exists() else 0
        headers = dict(UA, **({"Range": f"bytes={have}-"} if have else {}))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                resumed = bool(have) and r.status == 206
                total = _expected_total(r, have)
                with open(tmp, "ab" if resumed else "wb") as f:
                    shutil.copyfileobj(r, f, length=1 << 20)
            size = tmp.stat().st_size
            if total is not None and size != total:
                raise IOError(f"incomplete download: {size} of {total} bytes")
            if dest.suffix == ".gz" and not _gzip_ok(tmp):
                tmp.unlink()
                raise IOError("corrupt gzip stream; restarting from scratch")
            break
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"    retry {attempt + 1} for {dest.name} after {type(exc).__name__}: {exc}", flush=True)
            time.sleep(min(120, 10 * 2 ** attempt))
    tmp.replace(dest)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    return {"file": dest.name, "url": url, "bytes": dest.stat().st_size, "sha256": sha}


def _existing(dest: Path) -> dict | None:
    """Reuse an already-downloaded platform table (large, rarely changes)."""
    if dest.exists() and dest.stat().st_size > 0:
        return {"file": dest.name, "url": "(reused)", "bytes": dest.stat().st_size,
                "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()}
    return None


def platforms_in(matrix_gz: Path) -> set[str]:
    gpls: set[str] = set()
    with gzip.open(matrix_gz, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(("!Series_platform_id", "!Sample_platform_id")):
                gpls.update(re.findall(r"GPL\d+", line))
            if line.startswith("!series_matrix_table_begin"):
                break
    return gpls


def fetch(gse: str, out_root: Path, retries: int = 8) -> Path:
    out = out_root / gse
    listing = get(f"{GEO_FTP}/series/{stem(gse)}/{gse}/matrix/").decode("utf-8", errors="replace")
    files = sorted(set(re.findall(rf'href="({gse}(?:-GPL\d+)?_series_matrix\.txt\.gz)"', listing)))
    if not files:
        raise FileNotFoundError(f"no series matrix listed for {gse}")
    manifest = {"accession": gse, "downloaded": datetime.now(timezone.utc).isoformat(), "files": []}
    gpls: set[str] = set()
    for name in files:
        entry = download(f"{GEO_FTP}/series/{stem(gse)}/{gse}/matrix/{name}", out / name, retries)
        manifest["files"].append(entry)
        gpls |= platforms_in(out / name)
        print(f"  {name}: {entry['bytes'] / 1e6:.1f} MB")
    for gpl in sorted(gpls):
        dest = out / f"{gpl}.annot.txt"
        entry = _existing(dest) or download(GPL_TABLE.format(gpl=gpl), dest, retries)
        manifest["files"].append(entry)
        print(f"  {gpl} annotation: {entry['bytes'] / 1e6:.1f} MB")
    manifest["platforms"] = sorted(gpls)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return out / "manifest.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accessions", nargs="+")
    ap.add_argument("--out", type=Path, default=Path("data/raw/geo"))
    ap.add_argument("--retries", type=int, default=8)
    ap.add_argument("--pause", type=float, default=5.0, help="seconds between accessions (be polite to NCBI)")
    args = ap.parse_args(argv)
    for gse in args.accessions:
        print(f"{gse}:")
        print(f"  -> {fetch(gse, args.out, args.retries)}", flush=True)
        time.sleep(args.pause)
    return 0


if __name__ == "__main__":
    sys.exit(main())
