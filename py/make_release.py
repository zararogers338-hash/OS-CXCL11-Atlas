"""Build the public release archive and verify it before it leaves the machine.

    python py/make_release.py v0.1.0

Uses `git archive`, which honours `export-ignore` in .gitattributes, so private
working notes (docs/private/, manuscript/) and generated tool copies (.claude/)
never enter the archive. The archive is then scanned and the release is blocked if
it contains a private path or anything that looks like a credential.
"""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PATHS = re.compile(r"(^|/)(\.claude/|CLAUDE\.md$|docs/private/|manuscript/|\.Renviron$|\.env)")
SECRET_PATTERNS = {
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI-style API key": re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "assigned secret": re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
}
TEXT_SUFFIXES = {".py", ".R", ".r", ".smk", ".yaml", ".yml", ".md", ".txt", ".json", ".toml", ".cfg",
                 ".mplstyle", ".html", ".csv", ".tsv", ".ps1", ".sh", ""}
SELF = "py/make_release.py"  # names the patterns it scans for


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def scan(archive: Path) -> list[str]:
    problems = []
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            rel = name.split("/", 1)[1] if "/" in name else name
            if PRIVATE_PATHS.search(rel):
                problems.append(f"private path in archive: {rel}")
                continue
            if rel == SELF or name.endswith("/") or Path(rel).suffix not in TEXT_SUFFIXES:
                continue
            text = zf.read(name).decode("utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), 1):
                for label, rx in SECRET_PATTERNS.items():
                    if rx.search(line):
                        problems.append(f"possible {label} in {rel}:{lineno}")
    return problems


def main(version: str) -> int:
    if git("status", "--porcelain"):
        print("warning: working tree has uncommitted changes; the archive reflects HEAD only")
    out = ROOT / "release" / f"OS-CXCL11-Atlas-{version}.zip"
    out.parent.mkdir(exist_ok=True)
    git("archive", "--format=zip", f"--prefix=OS-CXCL11-Atlas-{version}/", "-o", str(out), "HEAD")
    problems = scan(out)
    for p in problems:
        print(p)
    if problems:
        out.unlink()
        print(f"RELEASE BLOCKED: {len(problems)} problem(s); archive deleted")
        return 1
    print(f"release OK: {out}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
