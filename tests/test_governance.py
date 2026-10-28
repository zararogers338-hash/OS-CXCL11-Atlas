"""Adversarial governance tests; all event writes use temporary projects."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ai/skills/cxcl11-osteosarcoma-tme/scripts/governance.py"
spec = importlib.util.spec_from_file_location("governance_under_test", SCRIPT)
gov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gov)


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.write("config/config.yaml", "project:\n  seed: 42\n")
        self.policy = gov.load_policy()

    def write(self, name, text="Independent validation evidence.\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return name

    def evidence(self, gate):
        items = []
        for kind, count in self.policy["gates"][int(gate[-1])]["required_evidence"].items():
            for index in range(count):
                path = self.write(f"evidence/{gate}-{kind}-{index}.txt")
                items.append(f"{kind}={path}")
        return items

    def propose(self, gate="gate0", actor="analyst"):
        return gov.propose(self.root, gate, self.evidence(gate), actor,
                           "research-steward", "Evidence prepared for independent review")

    def review(self, proposal, decision="pass", actor="independent-reviewer", role=None):
        gate = proposal["payload"]["gate"]
        role = role or self.policy["gates"][int(gate[-1])]["reviewer_roles"][0]
        report = self.write(f"reviews/{proposal['payload']['proposal_id']}.md", "I checked inputs, limitations and requirements.\n")
        return gov.review(self.root, proposal["payload"]["proposal_id"], decision,
                          actor, role, "Independent review completed", report)

    def approve(self, gate="gate0"):
        proposal = self.propose(gate)
        self.review(proposal)
        return proposal

    def board(self):
        report = gov.status(self.root)
        self.assertTrue(report["ledger_valid"], report)
        return {gate["id"]: gate for gate in report["gates"]}

    def ledger(self):
        return self.root / gov.LEDGER_PATH

    def test_historical_approval_never_auto_promoted(self):
        self.write("docs/private/decision_log.md", "## Gate 0\n- 决定：通过\n## Gate 2 Go/No-Go\n- 决定：待定\n")
        report = gov.status(self.root)
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["gates"][0]["status"], "ready")
        self.assertIn("historical", report["gates"][0]["historical_decision"])
        self.assertEqual(report["gates"][2]["historical_decision"], "pending (historical)")
        self.assertFalse(self.ledger().exists())

    def test_all_seven_gates_and_branching(self):
        for gate in gov.GATE_IDS[:5]:
            self.approve(gate)
        self.assertEqual(self.board()["gate5"]["status"], "ready")
        with self.assertRaises(gov.GovernanceError):
            self.propose("gate6")
        self.approve("gate5")
        self.approve("gate6")
        self.assertTrue(all(gate["status"] == "passed" for gate in self.board().values()))
        self.assertEqual(gov.status(self.root)["event_count"], 14)
        gov.revoke(self.root, "gate4", "steward", "research-steward", "Figures require correction")
        board = self.board()
        self.assertEqual(board["gate4"]["status"], "revoked")
        self.assertEqual(board["gate5"]["status"], "passed")
        self.assertEqual(board["gate6"]["status"], "blocked")

    def test_independent_review_role_and_normalized_identity(self):
        proposal = self.propose(actor="Alice")
        original = self.ledger().read_bytes()
        for actor in ("Alice", "ALICE", " ＡＬＩＣＥ "):
            with self.subTest(actor=actor), self.assertRaises(gov.GovernanceError):
                self.review(proposal, actor=actor)
        with self.assertRaises(gov.GovernanceError):
            self.review(proposal, role="bioinfo-analyst")
        self.assertEqual(self.ledger().read_bytes(), original)
        self.review(proposal)
        with self.assertRaises(gov.GovernanceError):
            self.review(proposal)

    def test_typed_evidence_required_empty_and_reused_file_rejected(self):
        file = self.write("evidence/shared.md")
        for evidence in ([f"novelty_report={file}"],
                         [f"novelty_report={file}", f"environment_report={file}"]):
            with self.subTest(evidence=evidence), self.assertRaises(gov.GovernanceError):
                gov.propose(self.root, "gate0", evidence, "a", "research-steward", "Check evidence")
        files = self.evidence("gate0")
        self.write(files[0].split("=", 1)[1], "")
        with self.assertRaises(gov.GovernanceError):
            gov.propose(self.root, "gate0", files, "a", "research-steward", "Check evidence")
        self.assertFalse(self.ledger().exists())

    def test_path_traversal_absolute_ads_and_symlink_rejected(self):
        for relative in ("../outside.txt", "/tmp/outside", "C:/outside", "a/../b", "a//b", "a\\b", "a:stream", "./evidence"):
            with self.subTest(relative=relative), self.assertRaises(gov.GovernanceError):
                gov._file_record(self.root, relative)
        self.write("inside.txt")
        try:
            os.symlink(self.root / "inside.txt", self.root / "link.txt")
        except OSError:
            return  # Windows without symlink privilege; other path attacks remain tested.
        with self.assertRaises(gov.GovernanceError):
            gov._file_record(self.root, "link.txt")

    def test_review_report_must_be_distinct_and_unchanged(self):
        proposal = self.propose()
        evidence_path = proposal["payload"]["evidence"][0]["path"]
        with self.assertRaises(gov.GovernanceError):
            gov.review(self.root, proposal["payload"]["proposal_id"], "pass", "reviewer", "reviewer-2", "Reviewed", evidence_path)
        review = self.review(proposal)
        self.write(review["payload"]["report"]["path"], "Report revised after approval")
        self.assertEqual(self.board()["gate0"]["status"], "stale")

    def test_evidence_change_invalidates_descendants(self):
        first = self.approve()
        self.approve("gate1")
        self.write(first["payload"]["evidence"][0]["path"], "Changed evidence after review")
        board = self.board()
        self.assertEqual(board["gate0"]["status"], "stale")
        self.assertEqual(board["gate1"]["status"], "blocked")
        self.assertIsNone(board["gate0"]["approval_hash"])
        self.assertIsNone(board["gate1"]["approval_hash"])
        with self.assertRaises(gov.GovernanceError):
            self.propose("gate2")

    def test_deleted_evidence_and_config_fail_closed(self):
        proposal = self.approve()
        (self.root / proposal["payload"]["evidence"][0]["path"]).unlink()
        self.assertEqual(self.board()["gate0"]["status"], "stale")
        (self.root / gov.CONFIG_PATH).unlink()
        self.assertFalse(gov.status(self.root)["ledger_valid"])

    def test_config_drift_requires_new_proposal(self):
        proposal = self.propose()
        self.write("config/config.yaml", "project:\n  seed: 99\n")
        self.assertEqual(self.board()["gate0"]["status"], "stale")
        with self.assertRaises(gov.GovernanceError):
            self.review(proposal)
        self.approve()
        self.assertEqual(self.board()["gate0"]["status"], "passed")

    def test_policy_drift_stales_approval_without_corrupting_history(self):
        self.approve()
        modified = json.loads(json.dumps(self.policy))
        modified["id"] += "-updated"
        policy_file = self.root / self.write("policy.json", json.dumps(modified))
        with patch.object(gov, "POLICY_PATH", policy_file):
            report = gov.status(self.root)
            self.assertTrue(report["ledger_valid"])
            self.assertEqual(report["gates"][0]["status"], "stale")

    def test_upstream_reapproval_does_not_resurrect_old_descendant(self):
        self.approve()
        self.approve("gate1")
        self.approve()  # A new proposal/approval generation, even with identical evidence.
        board = self.board()
        self.assertEqual(board["gate0"]["status"], "passed")
        self.assertEqual(board["gate1"]["status"], "stale")
        self.approve("gate1")
        self.assertEqual(self.board()["gate1"]["status"], "passed")

    def test_rejection_revocation_and_superseded_proposal(self):
        proposal = self.propose()
        current = self.propose()
        with self.assertRaises(gov.GovernanceError):
            self.review(proposal)
        self.review(current, decision="reject")
        self.assertEqual(self.board()["gate0"]["status"], "rejected")
        self.approve()
        with self.assertRaises(gov.GovernanceError):
            gov.revoke(self.root, "gate0", "analyst", "bioinfo-analyst", "Unauthorized")
        gov.revoke(self.root, "gate0", "steward", "research-steward", "Evidence correction")
        self.assertEqual(self.board()["gate0"]["status"], "revoked")
        self.approve()
        self.assertEqual(self.board()["gate0"]["status"], "passed")

    def test_malformed_tampered_duplicate_and_truncated_ledgers_fail_closed(self):
        self.approve()
        original = self.ledger().read_bytes()
        event = json.loads(original.splitlines()[0])
        event["actor"] = "tampered"
        variants = [b"", b"\n", b"not-json\n", original[:-1],
                    json.dumps(event).encode() + b"\n",
                    b'{"schema_version":1,"schema_version":1}\n',
                    b'{"schema_version":NaN}\n',
                    b'{"schema_version":1e999}\n']
        for raw in variants:
            with self.subTest(raw=raw[:60]):
                self.ledger().write_bytes(raw)
                report = gov.status(self.root)
                self.assertFalse(report["ledger_valid"])
                self.assertTrue(all(g["status"] == "invalid" for g in report["gates"]))
                with self.assertRaises((gov.GovernanceError, TypeError)):
                    self.propose()
                self.assertEqual(self.ledger().read_bytes(), raw)
        self.ledger().write_bytes(original)

    def test_rehashed_invalid_state_transition_is_rejected(self):
        self.approve()
        events = [json.loads(line) for line in self.ledger().read_text().splitlines()]
        events[-1]["actor"] = events[0]["actor"]
        unsigned = {key: value for key, value in events[-1].items() if key != "event_hash"}
        events[-1]["event_hash"] = gov._digest(unsigned)
        self.ledger().write_bytes(b"".join(gov._canonical(event) + b"\n" for event in events))
        self.assertFalse(gov.status(self.root)["ledger_valid"])

    def test_lock_contention_preserves_existing_lock_and_ledger(self):
        self.approve()
        original = self.ledger().read_bytes()
        lock = Path(str(self.ledger()) + ".lock")
        lock.write_text("owned by another writer")
        with self.assertRaises(gov.GovernanceError):
            self.propose()
        self.assertEqual(lock.read_text(), "owned by another writer")
        self.assertEqual(self.ledger().read_bytes(), original)

    def test_failed_atomic_replace_preserves_history_and_cleans_lock(self):
        self.approve()
        original = self.ledger().read_bytes()
        with patch.object(gov.os, "replace", side_effect=OSError("simulated interrupted commit")):
            with self.assertRaises(OSError):
                self.propose()
        self.assertEqual(self.ledger().read_bytes(), original)
        self.assertFalse(Path(str(self.ledger()) + ".lock").exists())
        self.assertFalse(list(self.ledger().parent.glob(".events-*.tmp")))

    def test_policy_cycles_and_gate_reviewer_bypass_rejected(self):
        policy = json.loads(json.dumps(self.policy))
        policy["gates"][0]["depends_on"] = ["gate6"]
        with self.assertRaises(gov.GovernanceError):
            gov._validate_policy(policy)
        policy = json.loads(json.dumps(self.policy))
        policy["gates"][4]["reviewer_roles"] = ["bioinfo-analyst"]
        with self.assertRaises(gov.GovernanceError):
            gov._validate_policy(policy)

    def test_portable_cli_and_stale_verification_exit_code(self):
        installed = self.root / "installed-skill"
        (installed / "scripts").mkdir(parents=True)
        (installed / "assets").mkdir()
        shutil.copy2(SCRIPT, installed / "scripts/governance.py")
        shutil.copy2(gov.POLICY_PATH, installed / "assets/governance-policy.json")
        command = [sys.executable, "-I", str(installed / "scripts/governance.py"), "--root", str(self.root)]
        check = subprocess.run(command + ["verify", "--json"], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertTrue(json.loads(check.stdout)["verification_ok"])
        proposal = self.approve()
        self.write(proposal["payload"]["evidence"][0]["path"], "drift")
        check = subprocess.run(command + ["verify", "--json"], capture_output=True, text=True)
        self.assertEqual(check.returncode, 2, check.stderr)
        self.assertFalse(json.loads(check.stdout)["verification_ok"])

    def test_verify_rejects_blocked_existing_proposal_but_not_unstarted_gates(self):
        self.approve()
        self.propose("gate1")
        gov.revoke(self.root, "gate0", "steward", "research-steward", "Correction required")
        self.assertEqual(self.board()["gate1"]["status"], "blocked")
        command = [sys.executable, str(SCRIPT), "--root", str(self.root), "verify", "--json"]
        check = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(check.returncode, 2, check.stderr)
        self.assertFalse(json.loads(check.stdout)["verification_ok"])


if __name__ == "__main__":
    unittest.main()
