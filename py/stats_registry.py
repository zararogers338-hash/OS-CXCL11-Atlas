"""Traceable statistics registry.

Every number that appears in the manuscript is recorded here by the script that
computed it. Parallel Snakemake jobs each write their own fragment
(results/stats/<fragment>.json); `collect` merges fragments into results/stats.json.

Python use:
    from stats_registry import StatsFragment
    with StatsFragment("A_clinical_km") as st:
        st.record("os_target_hr", 1.84, display="1.84", ci=(1.12, 3.02),
                  desc="TARGET-OS OS hazard ratio, CXCL11 high vs low")

CLI:
    python py/stats_registry.py collect results/stats/*.json -o results/stats.json
"""
from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAGMENT_DIR = ROOT / "results" / "stats"
KEY_RE = re.compile(r"^[a-z0-9_]+$")


def _text(value, field: str) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be a non-empty string without NUL characters")


def _name(value, field: str, *, mixed_case: bool = False) -> None:
    if not isinstance(value, str) or not KEY_RE.fullmatch(value.lower() if mixed_case else value):
        raise ValueError(f"{field} must be snake_case: {value!r}")


def _json_value(value, field: str) -> None:
    """Reject non-finite numbers even in optional metadata and nested values."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} contains a non-finite number")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _json_value(item, f"{field}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field} has a non-string JSON object key")
            _json_value(item, f"{field}.{key}")
        return
    raise ValueError(f"{field} contains a non-JSON value ({type(value).__name__})")


def validate_entry(key: str, entry, *, fragment: str | None = None) -> None:
    """Validate legacy Python/R entries without inventing missing provenance.

    A source path identifies the reported producer; it does not prove which
    revision, configuration or data produced an existing value. No hashes are
    inferred from today's files or required retroactively for legacy entries.
    """
    _name(key, "stat key")
    if not isinstance(entry, dict):
        raise ValueError(f"stat {key!r} must be an object")
    for field in ("value", "display", "desc", "source", "fragment"):
        if field not in entry:
            raise ValueError(f"stat {key!r} is missing {field!r}")
    _json_value(entry, f"stat {key!r}")
    value = entry["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"stat {key!r}.value must be a finite number or string")
    if isinstance(value, str):
        _text(value, f"stat {key!r}.value")
    for field in ("display", "desc", "source"):
        _text(entry[field], f"stat {key!r}.{field}")
    # R/utils_stats.R has always accepted names such as A_clinical_km.
    _name(entry["fragment"], f"stat {key!r}.fragment", mixed_case=True)
    if fragment is not None and entry["fragment"] != fragment:
        raise ValueError(f"stat {key!r}.fragment does not match payload fragment {fragment!r}")
    ci = entry.get("ci")
    if ci is not None:
        if (not isinstance(ci, (list, tuple)) or len(ci) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in ci)):
            raise ValueError(f"stat {key!r}.ci must contain two finite numbers or be null")
        if ci[0] > ci[1]:
            raise ValueError(f"stat {key!r}.ci lower bound exceeds upper bound")
    n = entry.get("n")
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 0):
        raise ValueError(f"stat {key!r}.n must be a non-negative integer or null")


def validate_registry(stats) -> None:
    if not isinstance(stats, dict):
        raise ValueError("stats registry must be an object")
    for key, entry in stats.items():
        validate_entry(key, entry)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite JSON number {value}")


def load_json(path: Path):
    """Read strict JSON: stdlib's permissive NaN and duplicate keys are errors."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"),
                          object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        _json_value(data, str(path))  # Also catches overflow, e.g. 1e999.
        return data
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _atomic_json(path: Path, data) -> None:
    """Publish a complete JSON file, leaving an old output intact on failure."""
    _json_value(data, str(path))
    serialized = json.dumps(data, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class StatsFragment:
    def __init__(self, name: str):
        _name(name, "fragment name", mixed_case=True)
        self.name = name
        self.path = FRAGMENT_DIR / f"{name}.json"
        self.entries: dict[str, dict] = {}
        caller = inspect.stack()[1].filename
        self.source = Path(caller).resolve().relative_to(ROOT).as_posix() if ROOT in Path(caller).resolve().parents else caller

    def record(self, key: str, value, *, desc: str, display: str | None = None,
               ci: tuple[float, float] | None = None, n: int | None = None) -> None:
        _name(key, "stat key")
        if key in self.entries:
            raise KeyError(f"duplicate stat key in fragment {self.name}: {key}")
        entry = {
            "value": value,
            "display": display if display is not None else _default_display(value),
            "ci": list(ci) if isinstance(ci, (tuple, list)) else ci,
            "n": n,
            "desc": desc,
            "source": self.source,
            "fragment": self.name,
        }
        validate_entry(key, entry, fragment=self.name)
        self.entries[key] = entry

    def write(self) -> Path:
        for key, entry in self.entries.items():
            validate_entry(key, entry, fragment=self.name)
        payload = {"fragment": self.name, "written": datetime.now(timezone.utc).isoformat(), "stats": self.entries}
        _atomic_json(self.path, payload)
        return self.path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.write()


def _default_display(value) -> str:
    if isinstance(value, float):
        if value != 0 and abs(value) < 0.001:
            return f"{value:.1e}"
        return f"{value:.3g}" if abs(value) < 100 else f"{value:.0f}"
    return str(value)


def collect(fragments: list[Path], out: Path) -> dict:
    merged: dict[str, dict] = {}
    seen_fragments: dict[str, Path] = {}
    for frag in sorted(fragments):
        data = load_json(frag)
        if not isinstance(data, dict) or "stats" not in data or "fragment" not in data:
            raise ValueError(f"{frag}: fragment payload must be an object with 'fragment' and 'stats'")
        name = data["fragment"]
        _name(name, f"{frag}: fragment name", mixed_case=True)
        if name in seen_fragments:
            raise ValueError(f"duplicate fragment {name!r} in {seen_fragments[name]} and {frag}")
        seen_fragments[name] = frag
        if "written" in data:
            _text(data["written"], f"{frag}: written")
        entries = data["stats"]
        # jsonlite serializes R's empty list() as []; nonempty entries are objects.
        if entries == []:
            entries = {}
        if not isinstance(entries, dict):
            raise ValueError(f"{frag}: stats must be an object (or an empty R list)")
        for key, entry in entries.items():
            try:
                validate_entry(key, entry, fragment=name)
            except ValueError as exc:
                raise ValueError(f"{frag}: {exc}") from exc
            if key in merged:
                raise KeyError(f"stat key {key!r} defined in both {merged[key]['fragment']} and {entry['fragment']}")
            merged[key] = entry
    _atomic_json(Path(out), dict(sorted(merged.items())))
    return merged


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="merge fragments into results/stats.json")
    c.add_argument("fragments", nargs="*", type=Path)
    c.add_argument("-o", "--out", type=Path, default=ROOT / "results" / "stats.json")
    args = ap.parse_args(argv)
    if args.cmd == "collect":
        try:
            merged = collect(args.fragments, args.out)
        except (ValueError, KeyError, OSError) as exc:
            print(f"stats registry: {exc}", file=sys.stderr)
            return 1
        print(f"collected {len(merged)} stats from {len(args.fragments)} fragments -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
