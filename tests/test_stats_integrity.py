"""Statistics integrity regression tests; all data and outputs are synthetic."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py"))
import audit_claims
import stats_registry as registry


def entry(**overrides):
    result = {"value": 1.2, "display": "1.20", "ci": [0.9, 1.5], "n": 10,
              "desc": "Synthetic effect estimate", "source": "R/synthetic.R",
              "fragment": "A_synthetic"}
    result.update(overrides)
    return result


class StatisticsIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def fragment_file(self, filename="fragment.json", **overrides):
        payload = {"fragment": "A_synthetic", "written": "2026-10-05 12:00:00 UTC",
                   "stats": {"synthetic_hr": entry()}}
        payload.update(overrides)
        path = self.root / filename
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def manuscript(self, text):
        path = self.root / "manuscript.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_legacy_r_fragment_collects_without_inferred_provenance(self):
        original = entry()
        out = self.root / "merged.json"
        merged = registry.collect([self.fragment_file()], out)
        self.assertEqual(merged, {"synthetic_hr": original})
        self.assertEqual(registry.load_json(out), merged)
        self.assertNotIn("source_sha256", merged["synthetic_hr"])

    def test_empty_r_fragment_remains_supported(self):
        result = registry.collect([self.fragment_file(stats=[])], self.root / "out.json")
        self.assertEqual(result, {})

    def test_python_fragment_roundtrip_and_duplicate_record(self):
        with patch.object(registry, "FRAGMENT_DIR", self.root):
            with registry.StatsFragment("A_synthetic") as fragment:
                fragment.record("synthetic_hr", 1.2, desc="Synthetic effect", ci=(0.9, 1.5), n=10)
                with self.assertRaises(KeyError):
                    fragment.record("synthetic_hr", 2, desc="Duplicate")
        data = registry.load_json(fragment.path)
        self.assertEqual(data["stats"]["synthetic_hr"]["ci"], [0.9, 1.5])
        registry.collect([fragment.path], self.root / "merged.json")

    def test_record_rejects_bad_values_before_mutating_entries(self):
        with patch.object(registry, "FRAGMENT_DIR", self.root):
            fragment = registry.StatsFragment("synthetic")
            for value in (float("nan"), float("inf"), -float("inf"), None, True, {}, [1]):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    fragment.record("estimate", value, desc="Synthetic")
            self.assertEqual(fragment.entries, {})

    def test_names_require_safe_strings_and_complete_match(self):
        for name in (None, 1, "../escape", "bad\n", "", "with space"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                registry.StatsFragment(name)
        for key in (None, 1, "Bad", "bad\n"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                registry.validate_entry(key, entry())

    def test_required_fields_and_safe_types(self):
        for field in ("value", "display", "source", "desc", "fragment"):
            broken = entry()
            del broken[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                registry.validate_entry("synthetic_hr", broken)
        for field in ("display", "source", "desc", "fragment"):
            for value in (None, 3, [], {}, "", " ", "bad\x00"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    registry.validate_entry("synthetic_hr", entry(**{field: value}))
        for value in ([], None, "not an entry", 4):
            with self.subTest(entry=value), self.assertRaises(ValueError):
                registry.validate_entry("synthetic_hr", value)

    def test_ci_and_n_are_validated(self):
        for ci in ([], [1], [1, 2, 3], [2, 1], [False, 1], [0, "1"], [0, float("inf")], "1,2"):
            with self.subTest(ci=ci), self.assertRaises(ValueError):
                registry.validate_entry("synthetic_hr", entry(ci=ci))
        for n in (-1, True, 2.5, "10", [], float("nan")):
            with self.subTest(n=n), self.assertRaises(ValueError):
                registry.validate_entry("synthetic_hr", entry(n=n))
        registry.validate_entry("synthetic_hr", entry(ci=None, n=0))
        registry.validate_entry("synthetic_hr", entry(value="not estimable", ci=None, n=None))

    def test_optional_metadata_cannot_hide_nonfinite_values(self):
        with self.assertRaisesRegex(ValueError, "non-finite"):
            registry.validate_entry("synthetic_hr", entry(metadata={"nested": [float("nan")]}))

    def test_strict_json_rejects_nonfinite_overflow_and_duplicates(self):
        path = self.root / "input.json"
        for text in ('{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}',
                     '{"a": 1e999}', '{"a": 1, "a": 2}', '{"nested": {"a": 1, "a": 2}}'):
            path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                registry.load_json(path)

    def test_duplicate_fragment_identity_is_rejected(self):
        first = self.fragment_file("one.json")
        second = self.fragment_file("two.json", stats={"other": entry()})
        with self.assertRaisesRegex(ValueError, "duplicate fragment"):
            registry.collect([first, second], self.root / "out.json")

    def test_duplicate_stat_across_fragments_is_rejected(self):
        first = self.fragment_file("one.json")
        second = self.fragment_file("two.json", fragment="B_synthetic",
                                    stats={"synthetic_hr": entry(fragment="B_synthetic")})
        with self.assertRaisesRegex(KeyError, "defined in both"):
            registry.collect([first, second], self.root / "out.json")

    def test_malformed_fragment_never_replaces_previous_output(self):
        out = self.root / "out.json"
        out.write_text("previous bytes", encoding="utf-8")
        cases = [[], {"fragment": "A_synthetic"},
                 {"fragment": "A_synthetic", "stats": [entry()]},
                 {"fragment": "A_synthetic", "stats": {"estimate": entry(fragment="other")}},
                 {"fragment": "A_synthetic", "stats": {"estimate": None}}]
        for payload in cases:
            path = self.root / "bad.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                registry.collect([path], out)
            self.assertEqual(out.read_text(encoding="utf-8"), "previous bytes")

    def test_failed_atomic_replace_preserves_fragment_and_cleans_temp(self):
        with patch.object(registry, "FRAGMENT_DIR", self.root):
            fragment = registry.StatsFragment("synthetic")
            fragment.record("estimate", 1, desc="Synthetic")
            fragment.write()
            before = fragment.path.read_bytes()
            fragment.record("other", 2, desc="Synthetic")
            def interrupted_replace(source, destination):
                payload = registry.load_json(source)
                self.assertIn("other", payload["stats"])
                self.assertEqual(Path(destination).read_bytes(), before)
                raise OSError("simulated interrupted publication")
            with patch.object(registry.os, "replace", side_effect=interrupted_replace):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    fragment.write()
            self.assertEqual(fragment.path.read_bytes(), before)
            self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_failed_atomic_replace_preserves_merged_file(self):
        path = self.fragment_file()
        out = self.root / "out.json"
        out.write_bytes(b"old merged file")
        with patch.object(registry.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                registry.collect([path], out)
        self.assertEqual(out.read_bytes(), b"old merged file")
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_write_revalidates_mutated_entries(self):
        with patch.object(registry, "FRAGMENT_DIR", self.root):
            fragment = registry.StatsFragment("synthetic")
            fragment.record("estimate", 1, desc="Synthetic")
            fragment.write()
            before = fragment.path.read_bytes()
            fragment.entries["estimate"]["value"] = float("nan")
            with self.assertRaises(ValueError):
                fragment.write()
            self.assertEqual(fragment.path.read_bytes(), before)

    def test_context_exception_does_not_write(self):
        with patch.object(registry, "FRAGMENT_DIR", self.root):
            with self.assertRaises(RuntimeError):
                with registry.StatsFragment("synthetic") as fragment:
                    fragment.record("estimate", 1, desc="Synthetic")
                    raise RuntimeError("analysis failed")
        self.assertFalse(fragment.path.exists())

    def test_well_formed_placeholders_audit_cleanly(self):
        path = self.manuscript("Effect {{stat:synthetic_hr}}; interval {{stat:synthetic_hr|ci}}.\n")
        self.assertEqual(audit_claims.audit([path], {"synthetic_hr": entry()}), [])

    def test_malformed_placeholders_are_reported(self):
        for token in ("{{stat:}}", "{{stat:bad-key}}", "{{stat:synthetic_hr|unknown}}",
                      "{{stat:synthetic_hr", "{{ stat:synthetic_hr}}", "{{STAT:synthetic_hr}}",
                      "{{stat :synthetic_hr}}", "{stat:synthetic_hr}}", "{{{stat:synthetic_hr}}}",
                      "{{stat:synthetic_hr}}}"):
            path = self.manuscript(f"Results: {token}\n")
            with self.subTest(token=token):
                problems = audit_claims.audit([path], {"synthetic_hr": entry()})
                self.assertEqual(len(problems), 1)
                self.assertIn(":1: malformed stat placeholder", problems[0])

    def test_adjacent_malformed_and_valid_placeholders_are_independent(self):
        path = self.manuscript("{{stat:bad|no}} {{stat:synthetic_hr}} {{stat:missing}}")
        problems = audit_claims.audit([path], {"synthetic_hr": entry()})
        self.assertEqual(len(problems), 2)
        self.assertIn("malformed stat placeholder", problems[0])
        self.assertIn("unknown stat key 'missing'", problems[1])

    def test_malformed_referenced_entries_report_context_without_crashing(self):
        path = self.manuscript("Effect {{stat:synthetic_hr|ci}}\n")
        for value in (None, [], 42, entry(ci=[]), entry(value=float("nan")), entry(source="")):
            with self.subTest(entry=value):
                problems = audit_claims.audit([path], {"synthetic_hr": value})
                self.assertEqual(len(problems), 1)
                self.assertIn(":1: malformed referenced stat", problems[0])

    def test_ci_requires_registered_interval(self):
        path = self.manuscript("Effect {{stat:synthetic_hr|ci}}")
        problems = audit_claims.audit([path], {"synthetic_hr": entry(ci=None)})
        self.assertEqual(len(problems), 1)
        self.assertIn("has no CI", problems[0])

    def test_code_mask_preserves_offsets_and_true_line_numbers(self):
        text = ("Introduction\n```python\nvalue = 1.23\n```\n"
                "Inline ``{{stat:bad-key}} and ` literal``\n"
                "~~~text\n{{stat:missing}}\n~~~\n"
                "Effect 1.23\nUnknown {{stat:missing}}\n")
        masked = audit_claims.strip_code(text)
        self.assertEqual(len(masked), len(text))
        self.assertEqual([i for i, c in enumerate(masked) if c == "\n"],
                         [i for i, c in enumerate(text) if c == "\n"])
        problems = audit_claims.audit([self.manuscript(text)], {})
        self.assertEqual(len(problems), 2)
        self.assertIn(":9: hand-typed", problems[0])
        self.assertIn(":10: unknown stat", problems[1])

    def test_multiline_inline_code_keeps_line_numbers(self):
        path = self.manuscript("Text `code\n1.23`\nResult 2.34\n")
        problems = audit_claims.audit([path], {})
        self.assertEqual(len(problems), 1)
        self.assertIn(":3: hand-typed", problems[0])

    def test_single_line_triple_backticks_do_not_hide_following_prose(self):
        path = self.manuscript("```{{stat:bad-key}}```\nResult 1.23\n")
        problems = audit_claims.audit([path], {})
        self.assertEqual(len(problems), 1)
        self.assertIn(":2: hand-typed", problems[0])

    def test_explicit_allow_and_citations_remain_supported(self):
        path = self.manuscript("Version 1.23 <!-- audit:allow -->\n"
                               "[@author2026] Figure 2A Table S3\n")
        self.assertEqual(audit_claims.audit([path], {}), [])

    def test_cli_rejects_invalid_stats_and_missing_files_clearly(self):
        path = self.manuscript("Plain prose")
        stats = self.root / "stats.json"
        for raw in ('{"x": NaN}', '{"x": {}, "x": {}}', "[]", '{"x": null}'):
            stats.write_text(raw, encoding="utf-8")
            stderr = io.StringIO()
            with self.subTest(raw=raw), contextlib.redirect_stderr(stderr):
                result = audit_claims.main([str(path), "--stats", str(stats)])
            self.assertEqual(result, 1)
            self.assertIn("cannot validate input", stderr.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(audit_claims.main([str(path), "--stats", str(self.root / "missing.json")]), 1)


if __name__ == "__main__":
    unittest.main()
