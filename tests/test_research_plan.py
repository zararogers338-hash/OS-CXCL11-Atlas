import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ai/skills/cxcl11-osteosarcoma-tme/scripts/research_plan.py"
spec = importlib.util.spec_from_file_location("portable_plan", SCRIPT)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


def test_plan_contracts_and_gate_prerequisites():
    plan = planner.load_plan()
    assert len(plan["tasks"]) >= 7
    assert all(t["acceptance"] for t in plan["tasks"])


def test_files_do_not_mark_science_complete(tmp_path):
    plan = planner.load_plan()
    for task in plan["tasks"]:
        for rel in task["deliverables"]:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("unreviewed", encoding="utf-8")
    report = planner.readiness(tmp_path, {"ledger_valid": True, "gates": []}, plan)
    assert all(t["completion"] == "not_inferred" for t in report["tasks"])
    assert all(t["state"] == "blocked" for t in report["tasks"] if t["requires_gates"])


def test_invalid_ledger_blocks_even_baseline_task(tmp_path):
    report = planner.readiness(tmp_path, {"ledger_valid": False, "gates": []})
    assert all(t["state"] == "blocked" for t in report["tasks"])


def test_only_passed_gate_unlocks_dependents(tmp_path):
    passed = planner.readiness(tmp_path, {"ledger_valid": True, "gates": [{"id": "gate0", "status": "passed"}]})
    stale = planner.readiness(tmp_path, {"ledger_valid": True, "gates": [{"id": "gate0", "status": "stale"}]})
    assert any(t["state"] == "ready" and t["requires_gates"] for t in passed["tasks"])
    assert all(t["state"] == "blocked" for t in stale["tasks"] if t["requires_gates"])


def test_plan_rejects_path_escape(tmp_path):
    import json
    plan = planner.load_plan()
    plan["tasks"][0]["deliverables"] = ["../outside"]
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="contained"):
        planner.load_plan(p)
