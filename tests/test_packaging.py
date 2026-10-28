"""Offline release/installer contract tests. Never starts Open-Science or touches its profile."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kit_builder", REPO / "py/build_ai_layer.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
PS = shutil.which("powershell.exe") or shutil.which("pwsh")
VERSION = "0.4.0"
SID = "cxcl11-osteosarcoma-tme"


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="os-kit-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        shutil.copytree(REPO / "ai", self.root / "ai", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(REPO / "LICENSE", self.root / "LICENSE")
        (self.root / "py").mkdir()
        (self.root / "py/governance.py").write_text("# isolated packaging fixture\n", encoding="utf-8")
        for relative in ("py/research_plan.py", "config/config.yaml", "workflow/Snakefile", ".Rprofile", "renv/activate.R", "renv/settings.json"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        self.original_root, self.original_ai = builder.ROOT, builder.AI
        builder.ROOT, builder.AI = self.root, self.root / "ai"
        self.addCleanup(self.restore_builder)

    def restore_builder(self):
        builder.ROOT, builder.AI = self.original_root, self.original_ai

    def packages(self):
        return builder.build_openscience(VERSION, "en") + builder.build_openscience(VERSION, "zh")

    def extracted_kit(self):
        archive = builder.build_kit(VERSION, self.packages(), None)
        destination = Path(self.temp.name) / "extracted"
        with zipfile.ZipFile(archive) as package:
            package.extractall(destination)  # archives created by this fixture, never arbitrary input
        return destination / archive.stem

    def ps(self, script: Path, *args: str, succeeds=True):
        if not PS:
            self.skipTest("PowerShell is unavailable")
        result = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-File", str(script), *map(str, args)], capture_output=True, timeout=90)
        output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
        if succeeds:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def rewrite_record(self, kit, relative):
        path = kit / relative
        manifest = json.loads((kit / "manifest.json").read_text(encoding="utf-8"))
        record = next(r for r in manifest["files"] if r["path"] == relative)
        record.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (kit / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_reproducible_archives_manifest_and_public_snapshot(self):
        packages = self.packages()
        self.assertEqual(len(packages), 14)
        first = {p.name: p.read_bytes() for p in packages}
        self.assertEqual(first, {p.name: p.read_bytes() for p in self.packages()})
        archive = builder.build_kit(VERSION, packages, None)
        before = archive.read_bytes()
        self.assertEqual(before, builder.build_kit(VERSION, packages, None).read_bytes())
        self.assertTrue(archive.with_suffix(".zip.sha256").is_file())
        with zipfile.ZipFile(archive) as zf:
            prefix = archive.stem + "/"
            manifest = json.loads(zf.read(prefix + "manifest.json"))
            records = {r["path"]: r for r in manifest["files"]}
            self.assertEqual(set(records), {n[len(prefix):] for n in zf.namelist()} - {"manifest.json"})
            self.assertIn("project/py/governance.py", records)
            self.assertFalse(any("private/" in name or "__pycache__/" in name for name in records))
            for name, record in records.items():
                content = zf.read(prefix + name)
                self.assertEqual(len(content), record["size"])
                self.assertEqual(hashlib.sha256(content).hexdigest(), record["sha256"])

    def test_strict_specialist_types(self):
        path = self.root / "ai/specialists/bioinfo-analyst.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for invalid in ("cxcl11-osteosarcoma-tme", [42], [SID, SID], None):
            with self.subTest(value=invalid):
                document = dict(original, skill_ids=invalid)
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValueError):
                    builder.validate("en")

    def test_duplicate_id_and_duplicate_json_property_rejected(self):
        path = self.root / "ai/specialists/bioinfo-analyst.json"
        original = path.read_text(encoding="utf-8")
        (path.parent / "duplicate.json").write_text(original, encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.validate("en")
        (path.parent / "duplicate.json").unlink()
        path.write_text(original.replace('"name":', '"name": "another-name", "name":', 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            builder.validate("en")

    def test_orphan_translation_rejected(self):
        source = self.root / "ai/locales/zh/specialists/bioinfo-analyst.json"
        shutil.copyfile(source, source.parent / "orphan.json")
        with self.assertRaisesRegex(ValueError, "set must equal"):
            builder.validate("zh")

    def test_private_path_and_credential_block_public_source(self):
        path = self.root / "ai/private"
        path.mkdir()
        (path / "notes.txt").write_text("not public", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "private path"):
            builder.public_project()
        (path / "notes.txt").unlink()
        path.rmdir()
        # Assemble the fake test credential to avoid embedding it in public source fixtures.
        (self.root / "py/unsafe.py").write_text("key = '" + "sk-" + "x" * 40 + "'", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "credential"):
            builder.public_project()

    def test_symlink_source_rejected(self):
        link = self.root / "ai/skills" / SID / "linked.txt"
        try:
            link.symlink_to(self.root / "LICENSE")
        except OSError:
            self.skipTest("Symlink creation requires unavailable host permission")
        with self.assertRaisesRegex(ValueError, "symlink"):
            builder.validate("en")

    def test_verify_only_has_no_profile_or_app_effect(self):
        kit = self.extracted_kit()
        profile = Path(self.temp.name) / "untouched-profile"
        output = self.ps(kit / "install_kit.ps1", "-VerifyOnly", "-OfflineProfileRoot", profile,
                         "-AppPath", str(Path(self.temp.name) / "missing-app.exe"))
        self.assertIn("Verified kit", output)
        self.assertFalse(profile.exists())

    def test_tamper_and_unmanifested_file_fail_before_install(self):
        kit = self.extracted_kit()
        profile = Path(self.temp.name) / "untouched-profile"
        path = kit / "LICENSE"
        original = path.read_bytes()
        path.write_bytes(original + b"tampered")
        self.ps(kit / "install_kit.ps1", "-OfflineProfileRoot", profile, succeeds=False)
        self.assertFalse(profile.exists())
        path.write_bytes(original)
        (kit / "unexpected.txt").write_text("unexpected", encoding="utf-8")
        self.ps(kit / "install_kit.ps1", "-OfflineProfileRoot", profile, succeeds=False)
        self.assertFalse(profile.exists())

    def test_missing_payload_fails_closed(self):
        kit = self.extracted_kit()
        (kit / "project/py/governance.py").unlink()
        self.ps(kit / "install_kit.ps1", "-VerifyOnly", succeeds=False)

    def test_tampered_helper_is_not_executed(self):
        kit = self.extracted_kit()
        helper = kit / "verify_kit.ps1"
        marker = Path(self.temp.name) / "executed.txt"
        helper.write_text(f"[IO.File]::WriteAllText('{marker}', 'should never execute')", encoding="utf-8-sig")
        output = self.ps(kit / "install_kit.ps1", "-VerifyOnly", succeeds=False)
        self.assertIn("helper hash/size mismatch", output)
        self.assertFalse(marker.exists())

    def test_malformed_nested_archives_fail_even_with_updated_manifest(self):
        kit = self.extracted_kit()
        relative = f"packages/en/{SID}-{VERSION}-en.zip"
        package = kit / relative
        original = package.read_bytes()
        cases = {
            "traversal": [(f"{SID}/../escape.txt", b"escape", 0o100644)],
            "absolute": [("C:/escape.txt", b"escape", 0o100644)],
            "case-duplicate": [(f"{SID}/skill.md", b"duplicate", 0o100644)],
            "prefix-collision": [(f"{SID}/a", b"a", 0o100644), (f"{SID}/A/b.txt", b"b", 0o100644)],
            "symlink": [(f"{SID}/link", b"elsewhere", 0o120777)],
            "unexpected-root": [("another-skill/a.txt", b"escape", 0o100644)],
        }
        for case, extra in cases.items():
            with self.subTest(case=case):
                package.write_bytes(original)
                with zipfile.ZipFile(package, "a") as archive:
                    for name, content, mode in extra:
                        entry = zipfile.ZipInfo(name)
                        entry.create_system = 3
                        entry.external_attr = mode << 16
                        archive.writestr(entry, content)
                self.rewrite_record(kit, relative)
                self.ps(kit / "install_kit.ps1", "-VerifyOnly", succeeds=False)

    def test_offline_install_and_update_preserve_existing_skill(self):
        kit = self.extracted_kit()
        profile = Path(self.temp.name) / "offline-profile"
        target = profile / "skills/imported" / SID
        target.mkdir(parents=True)
        (target / "user-original.txt").write_text("must survive", encoding="utf-8")
        self.ps(kit / "install_kit.ps1", "-Lang", "en", "-OfflineProfileRoot", profile)
        self.assertTrue((target / "SKILL.md").exists())
        backups = list(profile.glob("kit-transactions/*/previous-skill/user-original.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "must survive")
        receipts = list(profile.glob("kit-transactions/*/receipt.json"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())["state"], "committed")
        self.ps(kit / "install_kit.ps1", "-Lang", "zh", "-OfflineProfileRoot", profile)
        self.assertEqual(len(list(profile.glob("kit-transactions/*/receipt.json"))), 2)
        self.assertEqual(backups[0].read_text(), "must survive")

    def test_declared_zip_length_does_not_bypass_bounded_verification(self):
        kit = self.extracted_kit()
        relative = f"packages/en/{SID}-{VERSION}-en.zip"
        package = kit / relative
        added = f"{SID}/corrupt-length.txt"
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr(added, b"Z" * (2 << 20), compress_type=zipfile.ZIP_DEFLATED)
        data = bytearray(package.read_bytes())
        offset = data.index(b"PK\x01\x02")
        while data[offset:offset + 4] == b"PK\x01\x02":
            name_len, extra_len, comment_len = struct.unpack_from("<HHH", data, offset + 28)
            name = bytes(data[offset + 46:offset + 46 + name_len]).decode("utf-8")
            if name == added:
                struct.pack_into("<I", data, offset + 24, 1)
                break
            offset += 46 + name_len + extra_len + comment_len
        else:
            self.fail("could not locate central-directory fixture entry")
        package.write_bytes(data)
        self.rewrite_record(kit, relative)
        output = self.ps(kit / "install_kit.ps1", "-VerifyOnly", succeeds=False)
        self.assertIn("Decompressed ZIP size", output)

    def test_failed_app_registration_rolls_back_existing_skill(self):
        kit = self.extracted_kit()
        profile = Path(self.temp.name) / "rollback-profile"
        target = profile / "skills/imported" / SID
        target.mkdir(parents=True)
        (target / "original.txt").write_bytes(b"original installation")
        app = Path(self.temp.name) / "fake-app.cmd"
        cli = app.parent / "resources/cli/index.mjs"
        cli.parent.mkdir(parents=True)
        cli.write_text("// inert test placeholder", encoding="utf-8")
        status = json.dumps({"running": True, "configRoot": str(profile)})
        app.write_text('@echo off\nif "%~2"=="status" (\n  echo ' + status +
                       '\n  exit /b 0\n)\nif "%~2"=="doctor" (\n  echo simulated-registration-failure\n  exit /b 7\n)\nexit /b 99\n', encoding="ascii")
        output = self.ps(kit / "install_kit.ps1", "-AppPath", app, succeeds=False)
        self.assertIn("simulated-registration-failure", output)
        self.assertEqual((target / "original.txt").read_bytes(), b"original installation")
        self.assertFalse((target / "SKILL.md").exists())
        self.assertEqual(len(list(profile.glob("kit-transactions/*/failed-skill/SKILL.md"))), 1)
        self.assertEqual(len(list(profile.glob("kit-transactions/*/receipt.json"))), 0)


if __name__ == "__main__":
    unittest.main()
