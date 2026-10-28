"""Audit manuscript numbers against results/stats.json.

Manuscript sources reference statistics as {{stat:key}} (display value) or
{{stat:key|ci}} (display value with 95% CI). This audit fails if:
  1. a referenced key is missing from stats.json;
  2. a placeholder or its referenced statistics entry is malformed;
  3. a hand-typed statistic appears outside a placeholder (decimals, p-values,
     percentages, HR/OR/AUC/C-index values) -- such numbers are untraceable.

Lines containing `audit:allow` are skipped (e.g. gene names like IL-2, reagent
versions). Usage:
    python py/audit_claims.py manuscript/*.md --stats results/stats.json
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from stats_registry import load_json, validate_entry, validate_registry

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\{\{stat:([a-z0-9_]+)(\|ci)?\}\}")
PLACEHOLDER_START = re.compile(r"\{+[ \t]*stat\b", re.I)
HAND_TYPED = [
    re.compile(r"\b[Pp]\s*[<=>≤]\s*0?\.\d+"),
    re.compile(r"\b(?:HR|OR|AUC|C-index|r|rho|ρ)\s*[=:]\s*-?\d"),
    re.compile(r"(?<![\w.])-?\d+\.\d+(?![\w.])"),
    re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s?%"),
]


def strip_code(text: str) -> str:
    """Mask Markdown code while preserving all original line/column offsets."""
    def mask(value: str) -> str:
        return re.sub(r"[^\r\n]", " ", value)

    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        if fence is not None:
            lines.append(mask(line))
            if re.fullmatch(r"[ \t]{0,3}" + re.escape(fence[0]) +
                            r"{" + str(fence[1]) + r",}[ \t]*(?:\r?\n)?", line):
                fence = None
            continue
        opening = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", line)
        # A backtick fence's info string cannot itself contain backticks;
        # otherwise a one-line ```code``` span would hide later prose.
        if opening and opening.group(1)[0] == "`" and "`" in line[opening.end():]:
            opening = None
        if opening:
            marker = opening.group(1)
            fence = (marker[0], len(marker))
            lines.append(mask(line))
        else:
            lines.append(line)
    text = "".join(lines)
    # Match same-length backtick delimiters, including multiline code spans.
    return re.sub(r"(?<!`)(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)",
                  lambda match: mask(match.group(0)), text)


def _placeholder_spans(line: str):
    """Recognize intended tokens too, so malformed syntax cannot evade audit."""
    starts = list(PLACEHOLDER_START.finditer(line))
    for index, start in enumerate(starts):
        limit = starts[index + 1].start() if index + 1 < len(starts) else len(line)
        closing = re.search(r"\}+", line[start.end():limit])
        end = start.end() + closing.end() if closing else limit
        yield start.start(), end, line[start.start():end]


def audit(files: list[Path], stats: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(stats, dict):
        return ["stats registry must be an object"]
    for f in files:
        text = strip_code(Path(f).read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), 1):
            if "audit:allow" in line or line.lstrip().startswith(("<!--", "#|")):
                continue
            bare = list(line)
            for start, end, token in _placeholder_spans(line):
                bare[start:end] = " " * (end - start)
                m = PLACEHOLDER.fullmatch(token)
                if m is None:
                    problems.append(f"{f}:{lineno}: malformed stat placeholder {token!r}")
                    continue
                key = m.group(1)
                if key not in stats:
                    problems.append(f"{f}:{lineno}: unknown stat key '{key}'")
                    continue
                try:
                    validate_entry(key, stats[key])
                except ValueError as exc:
                    problems.append(f"{f}:{lineno}: malformed referenced stat '{key}': {exc}")
                    continue
                if m.group(2) and stats[key].get("ci") is None:
                    problems.append(f"{f}:{lineno}: '{key}' requested with |ci but has no CI")
            bare = "".join(bare)
            bare = re.sub(r"\[@[^\]]+\]", "", bare)                     # citations
            bare = re.sub(r"(?i)\b(fig(ure)?s?|table|supplementary)\s*S?\d+[a-z]?", "", bare)
            flagged: list[tuple[int, int]] = []
            for rx in HAND_TYPED:
                for m in rx.finditer(bare):
                    if any(m.start() < e and s < m.end() for s, e in flagged):
                        continue
                    flagged.append(m.span())
                    problems.append(f"{f}:{lineno}: hand-typed number '{m.group(0).strip()}' (use {{{{stat:key}}}})")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--stats", type=Path, default=ROOT / "results" / "stats.json")
    args = ap.parse_args(argv)
    try:
        stats = load_json(args.stats)
        validate_registry(stats)
        problems = audit(args.files, stats)
    except (ValueError, OSError) as exc:
        print(f"audit: cannot validate input: {exc}", file=sys.stderr)
        return 1
    for p in problems:
        print(p)
    print(f"audit: {len(problems)} problem(s) in {len(args.files)} file(s); {len(stats)} stats available")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
