"""Build the open AI layer from ai/ (the single source of truth), in English and Chinese.

    python py/build_ai_layer.py openscience   # release/ai/*-<lang>.zip + the bundle, importable into AIPOCH Open-Science
    python py/build_ai_layer.py claude        # .claude/skills/ + .claude/agents/ for Claude Code (--lang zh by default)
    python py/build_ai_layer.py all
    options: --lang en|zh|all   (openscience default: all; claude default: zh)

ai/skills/<skill-id>/                 canonical skill (English): SKILL.md, references/, scripts/
ai/specialists/<id>.json              canonical specialists (English; Open-Science specialist.json fields only)
ai/locales/<lang>/skills/<skill-id>/  translated SKILL.md + references/ (scripts are shared from the canonical skill)
ai/locales/<lang>/specialists/<id>.json  translated text fields; ids, skills and connectors must match the canonical file
ai/INSTALL.md                         bilingual installation guide shipped in the bundle
ai/VERSION                            SemVer shared by every package

The analysis pipeline never depends on this layer; it only packages the
agent instructions that help run and document the pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "ai"
LANGS = ["en", "zh"]
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Open-Science silently skips user Skills/Specialists whose ids start with these (reserved for the app).
RESERVED_PREFIXES = ("os-", "mcp-")


def check_id(kind: str, value: str) -> None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{kind} '{value}' must be lowercase kebab-case")
    if value.startswith(RESERVED_PREFIXES):
        raise ValueError(f"{kind} '{value}' uses a prefix reserved by Open-Science {RESERVED_PREFIXES}")
SPECIALIST_KEYS = ["name", "display_name", "description", "system_prompt", "skill_ids", "connector_ids"]
TEXT_KEYS = {"display_name", "description", "system_prompt"}
OPENSCIENCE_APP_VERSION = "0.35.0"  # app version the packages were checked against
ZIP_DATE = (1980, 1, 1, 0, 0, 0)    # fixed timestamps -> byte-reproducible archives

# Claude Code needs an explicit tool list per agent; Open-Science manages permissions in the app.
CLAUDE_TOOLS = {
    "research-steward": "Read, Write, Edit, Glob, Grep, Bash, PowerShell",
    "reproducibility-auditor": "Read, Glob, Grep, Bash, PowerShell",
    "bioinfo-analyst": "Read, Write, Edit, Glob, Grep, Bash, PowerShell",
    "figure-artist": "Read, Write, Edit, Glob, Grep, Bash, PowerShell",
    "manuscript-writer": "Read, Write, Edit, Glob, Grep, Bash, PowerShell, WebFetch",
    "reviewer-2": "Read, Glob, Grep, Bash, PowerShell",
}


def frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.S)
    if not m:
        raise ValueError(f"{skill_md}: missing YAML frontmatter")
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or (path.exists() and bool(
        getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def _assert_source(path: Path) -> None:
    if _is_reparse(path):
        raise ValueError(f"symlink/junction cannot be packaged: {path}")
    if not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"source escapes repository: {path}")
    for parent in path.parents:
        if parent == ROOT.parent:
            break
        if _is_reparse(parent):
            raise ValueError(f"symlink/junction cannot be packaged: {parent}")


def _files(root: Path) -> dict[str, Path]:
    _assert_source(root)
    files = {}
    if not root.exists():
        return files
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            _assert_source(Path(current) / name)
        dirs[:] = sorted(d for d in dirs if d not in {"__pycache__", ".pytest_cache"})
        for name in sorted(names):
            path = Path(current) / name
            _assert_source(path)
            if path.suffix not in {".pyc", ".pyo"}:
                files[path.relative_to(root).as_posix()] = path
    return dict(sorted(files.items()))


def _unique_json(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON property: {key}")
        out[key] = value
    return out


def _load_specialist(path: Path) -> dict:
    _assert_source(path)
    spec = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json)
    if not isinstance(spec, dict) or set(spec) != set(SPECIALIST_KEYS):
        raise ValueError(f"{path.name}: exact specialist fields required: {SPECIALIST_KEYS}")
    for key in ["name", *sorted(TEXT_KEYS)]:
        if not isinstance(spec[key], str) or not spec[key].strip():
            raise ValueError(f"{path.name}: {key} must be a nonempty string")
    for key in ("skill_ids", "connector_ids"):
        values = spec[key]
        if not isinstance(values, list) or any(not isinstance(v, str) or not ID_RE.fullmatch(v) for v in values):
            raise ValueError(f"{path.name}: {key} must be a list of kebab-case strings")
        if len(values) != len(set(values)):
            raise ValueError(f"{path.name}: duplicate {key}")
    if not spec["skill_ids"]:
        raise ValueError(f"{path.name}: at least one skill_id required")
    check_id("specialist", spec["name"])
    if path.stem != spec["name"]:
        raise ValueError(f"{path.name}: filename must match specialist name")
    return spec


def skill_tree(sid: str, lang: str) -> dict[str, Path]:
    """Canonical files, overlaid by the locale's translated documents."""
    files = _files(AI / "skills" / sid)
    if lang != "en":
        loc = AI / "locales" / lang / "skills" / sid
        translated = _files(loc)
        docs = {k for k in files if k.endswith(".md")}
        missing, extra = docs - set(translated), set(translated) - docs
        if missing or extra:
            raise ValueError(f"{lang} translation of {sid}: missing {sorted(missing)}, unexpected {sorted(extra)}")
        files.update(translated)
    return files


def load_specialists(lang: str) -> dict[str, dict]:
    specs = {}
    canonical = sorted((AI / "specialists").glob("*.json"))
    if lang != "en":
        localized = AI / "locales" / lang / "specialists"
        if {p.name for p in localized.glob("*.json")} != {p.name for p in canonical}:
            raise ValueError(f"{lang}: translated specialist set must equal canonical set")
    for f in canonical:
        spec = _load_specialist(f)
        if lang != "en":
            loc_file = AI / "locales" / lang / "specialists" / f.name
            if not loc_file.exists():
                raise ValueError(f"missing {lang} translation: {loc_file.relative_to(ROOT)}")
            loc = _load_specialist(loc_file)
            for k in set(SPECIALIST_KEYS) - TEXT_KEYS:
                if loc.get(k) != spec.get(k):
                    raise ValueError(f"{loc_file.name}: '{k}' differs from the canonical specialist")
            spec = loc
        if spec["name"] in specs:
            raise ValueError(f"duplicate specialist id: {spec['name']}")
        specs[spec["name"]] = spec
    return specs


def validate(lang: str) -> tuple[dict[str, dict[str, Path]], dict[str, dict]]:
    if lang not in LANGS:
        raise ValueError(f"unsupported locale: {lang}")
    skills = {}
    if lang != "en":
        expected = {p.name for p in (AI / "skills").iterdir() if p.is_dir()}
        actual = {p.name for p in (AI / "locales" / lang / "skills").iterdir() if p.is_dir()}
        if expected != actual:
            raise ValueError(f"{lang}: translated skill set must equal canonical set")
    for d in sorted(p for p in (AI / "skills").iterdir() if p.is_dir()):
        tree = skill_tree(d.name, lang)
        fm = frontmatter(tree["SKILL.md"])
        check_id("skill", d.name)
        if fm.get("name") != d.name:
            raise ValueError(f"skill {d.name} ({lang}): frontmatter name must equal the directory name")
        if not fm.get("description"):
            raise ValueError(f"skill {d.name} ({lang}): description is required")
        skills[d.name] = tree
    specialists = load_specialists(lang)
    for name, spec in specialists.items():
        extra = set(spec) - set(SPECIALIST_KEYS)
        if extra:
            raise ValueError(f"{name}: unknown fields {sorted(extra)} (Open-Science rejects them)")
        check_id("specialist", name)
        missing = [s for s in spec["skill_ids"] if s not in skills]
        if missing:
            raise ValueError(f"{name}: unknown skill ids {missing}")
        if any(not ID_RE.match(c) for c in spec.get("connector_ids", [])):
            raise ValueError(f"{name}: connector ids must be kebab-case")
    return skills, specialists


def _write(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data, compresslevel=9)


def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def build_openscience(version: str, lang: str) -> list[Path]:
    skills, specialists = validate(lang)
    out_dir = ROOT / "release" / "ai"
    out_dir.mkdir(parents=True, exist_ok=True)
    built = []
    for sid, tree in skills.items():  # standalone Skill packages
        path = out_dir / f"{sid}-{version}-{lang}.zip"
        with zipfile.ZipFile(path, "w") as zf:
            for rel, src in tree.items():
                _write(zf, f"{sid}/{rel}", src.read_bytes())
        built.append(path)
    for name, spec in specialists.items():  # Specialist packages (App-export layout)
        path = out_dir / f"{name}-{version}-{lang}.zip"
        manifest = {"schema_version": 1, "id": name, "version": version,
                    "exported_with_app_version": OPENSCIENCE_APP_VERSION}
        ordered = {k: spec[k] for k in SPECIALIST_KEYS if k in spec}
        with zipfile.ZipFile(path, "w") as zf:
            _write(zf, "manifest.json", _json_bytes(manifest))
            _write(zf, "specialist.json", _json_bytes(ordered))
            for sid in spec["skill_ids"]:
                for rel, src in skills[sid].items():
                    _write(zf, f"skills/{sid}/{rel}", src.read_bytes())
            _write(zf, "README.txt", (
                f"{spec.get('display_name', name)} {version} ({lang})\n"
                "Part of the OS-CXCL11 Atlas open AI layer (MIT). Source: ai/ in the project repository.\n"
                "This package contains no credentials; models and connectors are configured by the user in the app.\n"
            ).encode("utf-8"))
        built.append(path)
    return built


PUBLIC_DIRS = ("config", "workflow", "py", "R", "style", "tests", "ai", "docs/data_cards")
PUBLIC_FILES = ("README.md", "AGENTS.md", "LICENSE", "pyproject.toml", "uv.lock", "renv.lock",
                ".Rprofile", "renv/activate.R", "renv/settings.json", "docs/ARCHITECTURE.md", "docs/RELEASE-0.4.0.md")
PRIVATE_PARTS = {"private", "data", "results", "logs", ".git", ".venv", ".claude", "manuscript",
                 ".env", ".renviron", "credentials", "secrets"}
SECRET_PATTERNS = (
    re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"\bsk-[A-Za-z0-9]{32,}"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def public_project() -> dict[str, Path]:
    """Explicit public source roots; no scientific data/results or private research notes."""
    files = {}
    for directory in PUBLIC_DIRS:
        for rel, src in _files(ROOT / directory).items():
            name = f"{directory}/{rel}"
            if any(p.lower() in PRIVATE_PARTS or p.lower().startswith(".env") for p in Path(name).parts):
                raise ValueError(f"private path in public source: {name}")
            files[name] = src
    for name in PUBLIC_FILES:
        path = ROOT / name
        if path.exists():
            _assert_source(path)
            files[name] = path
    for name, path in files.items():
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise ValueError(f"possible credential in public source: {name}")
    return dict(sorted(files.items()))


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _release_payload(version: str, packages: list[Path], installer: Path | None) -> dict[str, Path | bytes]:
    payload: dict[str, Path | bytes] = {
        "INSTALL.md": AI / "INSTALL.md", "LICENSE": ROOT / "LICENSE",
        **{name: src for name, src in _files(AI / "openscience").items()},
        **{f"project/{name}": src for name, src in public_project().items()},
    }
    for package in sorted(packages):
        lang = package.stem.rsplit("-", 1)[1]
        payload[f"packages/{lang}/{package.name}"] = package
    if installer:
        _assert_source(installer)
        if not re.fullmatch(r"aipoch-open-science-\d+\.\d+\.\d+-win-x64-setup\.exe", installer.name):
            raise ValueError("installer must use the official Windows x64 release filename")
        license_file = ROOT / "release/vendor/Open-Science-LICENSE.txt"
        if not license_file.is_file():
            raise FileNotFoundError(f"required third-party license: {license_file}")
        payload[f"installer/{installer.name}"] = installer
        payload["third_party/Open-Science-LICENSE.txt"] = license_file
        payload["third_party/README.txt"] = (
            f"AIPOCH Open-Science {OPENSCIENCE_APP_VERSION}: https://github.com/aipoch/open-science/releases\n"
            "The vendor executable is copied without modification; installation checks its Authenticode signature.\n"
            "Redistributed under Apache-2.0. OS-CXCL11 Atlas is independent of AIPOCH.\n"
        ).encode("utf-8")
    return dict(sorted(payload.items()))


def _build_distribution(version: str, packages: list[Path], installer: Path | None, kit: bool) -> Path:
    prefix = "OS-CXCL11-OpenScience-Kit" if kit else "OS-CXCL11-AI-pack"
    root = f"{prefix}-{version}"
    path = ROOT / "release/ai" / f"{root}.zip"
    payload = _release_payload(version, packages, installer)
    records = []
    for name, src in payload.items():
        if isinstance(src, Path):
            _assert_source(src)
            size, digest = src.stat().st_size, _sha256(src)
        else:
            size, digest = len(src), hashlib.sha256(src).hexdigest()
        records.append({"path": name, "size": size, "sha256": digest})
    manifest = {"schema_version": 1, "version": version, "hash_algorithm": "sha256", "files": records}
    # Atomic publication avoids leaving a plausible but truncated final release after a failed build.
    temporary = path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w") as zf:
            for name, src in payload.items():
                if name.startswith("installer/"):
                    info = zipfile.ZipInfo(f"{root}/{name}", date_time=ZIP_DATE)
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    info.compress_type = zipfile.ZIP_STORED
                    with src.open("rb") as stream, zf.open(info, "w", force_zip64=True) as target:
                        shutil.copyfileobj(stream, target, 1 << 20)
                else:
                    _write(zf, f"{root}/{name}", src.read_bytes() if isinstance(src, Path) else src)
            _write(zf, f"{root}/manifest.json", _json_bytes(manifest))
        temporary.replace(path)
        path.with_suffix(".zip.sha256").write_text(f"{_sha256(path)}  {path.name}\n", encoding="ascii")
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def build_bundle(version: str, packages: list[Path]) -> Path:
    return _build_distribution(version, packages, None, False)


def build_kit(version: str, packages: list[Path], installer: Path | None) -> Path:
    return _build_distribution(version, packages, installer, True)


def build_claude(lang: str) -> list[Path]:
    skills, specialists = validate(lang)
    built = []
    for sid, tree in skills.items():
        dst = ROOT / ".claude" / "skills" / sid
        _assert_source(dst)
        if dst.exists():
            shutil.rmtree(dst)
        for rel, src in tree.items():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst / rel)
        built.append(dst)
    agents_dst = ROOT / ".claude" / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    for name, spec in specialists.items():
        desc = spec["description"].replace("\n", " ")
        body = (f"---\nname: {name}\ndescription: {desc}\ntools: {CLAUDE_TOOLS.get(name, 'Read, Glob, Grep')}\n---\n\n"
                f"<!-- Generated from ai/ ({lang}) by py/build_ai_layer.py; edit ai/, not this file. -->\n\n"
                f"{spec['system_prompt']}\n")
        path = agents_dst / f"{name}.md"
        path.write_text(body, encoding="utf-8")
        built.append(path)
    return built


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=["openscience", "kit", "claude", "all"], nargs="?", default="all")
    ap.add_argument("--lang", choices=[*LANGS, "all"], default=None)
    ap.add_argument("--installer", type=Path, default=None,
                    help="official Open-Science setup.exe to embed in the kit (default: release/vendor/*setup.exe)")
    args = ap.parse_args(argv)
    version = (AI / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"ai/VERSION is not SemVer: {version!r}")
    if args.target in {"openscience", "kit", "all"}:
        langs = LANGS if args.lang in (None, "all") else [args.lang]
        packages = []
        for lang in langs:
            packages += build_openscience(version, lang)
        for p in packages:
            print(f"  open-science  {p.relative_to(ROOT)}")
        if len(langs) == len(LANGS):
            print(f"  bundle        {build_bundle(version, packages).relative_to(ROOT)}")
        if args.target == "kit":
            installer = args.installer or next(iter(sorted((ROOT / "release" / "vendor").glob("*setup.exe"))), None)
            kit = build_kit(version, packages, installer)
            print(f"  kit           {kit.relative_to(ROOT)}  (installer: {installer.name if installer else 'not embedded'})")
    if args.target in {"claude", "all"}:
        lang = "zh" if args.lang in (None, "all") else args.lang
        for p in build_claude(lang):
            print(f"  claude-code   {p.relative_to(ROOT)}  ({lang})")
    print(f"ai layer v{version}: validated and built")
    return 0


if __name__ == "__main__":
    sys.exit(main())
