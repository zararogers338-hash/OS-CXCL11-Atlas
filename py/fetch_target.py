"""Download TARGET-OS expression (UCSC Xena GDC hub) and clinical supplements (GDC API).

    python py/fetch_target.py --out data/raw/target_os

Expression: STAR TPM + counts from the Xena GDC hub. Clinical: every open-access
"Clinical Supplement" XLSX for TARGET-OS from the GDC API (Discovery + Validation
tables carry OS/EFS fields); the Xena clinical/survival tables are kept for
cross-checking. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from fetch_geo import download, get

XENA = "https://gdc-hub.s3.us-east-1.amazonaws.com/download/{name}"
XENA_FILES = ["TARGET-OS.star_tpm.tsv.gz", "TARGET-OS.star_counts.tsv.gz",
              "TARGET-OS.clinical.tsv.gz", "TARGET-OS.survival.tsv.gz",
              "gencode.v36.annotation.gtf.gene.probemap"]
GDC_FILES = "https://api.gdc.cancer.gov/files"
GDC_DATA = "https://api.gdc.cancer.gov/data/{file_id}"


def gdc_clinical_files() -> list[dict]:
    filters = {"op": "and", "content": [
        {"op": "in", "content": {"field": "cases.project.project_id", "value": ["TARGET-OS"]}},
        {"op": "in", "content": {"field": "data_type", "value": ["Clinical Supplement"]}},
        {"op": "in", "content": {"field": "access", "value": ["open"]}},
    ]}
    query = urllib.parse.urlencode({"filters": json.dumps(filters), "fields": "file_id,file_name,file_size",
                                    "size": 100, "format": "JSON"})
    return json.loads(get(f"{GDC_FILES}?{query}"))["data"]["hits"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/raw/target_os"))
    args = ap.parse_args(argv)
    manifest = {"accession": "TARGET-OS", "downloaded": datetime.now(timezone.utc).isoformat(), "files": []}
    for name in XENA_FILES:
        entry = download(XENA.format(name=name), args.out / name)
        manifest["files"].append(entry)
        print(f"  {name}: {entry['bytes'] / 1e6:.2f} MB")
    for hit in gdc_clinical_files():
        entry = download(GDC_DATA.format(file_id=hit["file_id"]), args.out / "clinical" / hit["file_name"])
        entry["gdc_file_id"] = hit["file_id"]
        manifest["files"].append(entry)
        print(f"  clinical/{hit['file_name']}: {entry['bytes'] / 1e3:.0f} kB")
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"  -> {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
