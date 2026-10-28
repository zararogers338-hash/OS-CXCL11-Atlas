"""Read-only research readiness planner. File presence never means scientific completion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PLAN = Path(__file__).resolve().parent.parent / "assets" / "research-plan.json"


def load_plan(path: Path = PLAN) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or not isinstance(plan.get("tasks"), list):
        raise ValueError("unsupported research plan")
    ids = set()
    for task in plan["tasks"]:
        required = {"id", "title_en", "title_zh", "owner", "reviewer", "requires_gates", "code", "deliverables", "acceptance", "acceptance_zh"}
        if not isinstance(task, dict) or not required <= task.keys():
            raise ValueError("incomplete task contract")
        if not isinstance(task["id"], str) or not task["id"] or task["id"] in ids:
            raise ValueError("invalid or duplicate task id")
        ids.add(task["id"])
        if task["owner"] == task["reviewer"]:
            raise ValueError("task requires independent review role")
        for field in ("requires_gates", "code", "deliverables", "acceptance", "acceptance_zh"):
            if not isinstance(task[field], list) or any(not isinstance(x, str) or not x for x in task[field]):
                raise ValueError(f"invalid {field}")
        if any(g not in {f"gate{i}" for i in range(7)} for g in task["requires_gates"]):
            raise ValueError("unknown gate prerequisite")
        for rel in task["code"] + task["deliverables"]:
            if Path(rel).is_absolute() or ".." in Path(rel).parts or "\\" in rel or ":" in rel:
                raise ValueError("plan paths must be relative and contained")
    return plan


def _present(root: Path, rel: str) -> bool:
    p = root / rel
    return p.resolve().is_relative_to(root.resolve()) and p.is_file() and p.stat().st_size > 0


def readiness(root: Path, gate_report: dict, plan: dict | None = None) -> dict:
    plan = load_plan() if plan is None else plan
    passed = {g["id"] for g in gate_report.get("gates", []) if g.get("status") == "passed"}
    valid = gate_report.get("ledger_valid") is True
    tasks = []
    for task in plan["tasks"]:
        blockers = [f"requires verified {gate}" for gate in task["requires_gates"] if gate not in passed]
        if not valid:
            blockers.insert(0, "governance ledger is invalid or unverified")
        missing = [p for p in task["code"] if not _present(root, p)]
        tasks.append({**task, "state": "blocked" if blockers else "ready",
                      "blockers": blockers, "missing_implementation": missing,
                      "present_deliverables": [p for p in task["deliverables"] if _present(root, p)],
                      "completion": "not_inferred"})
    return {"schema_version": 1, "ledger_valid": valid,
            "notice": "Readiness is permission to prepare work, not proof of task completion or scientific validity.",
            "tasks": tasks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--lang", choices=["en", "zh"], default="en")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    from governance import status
    report = readiness(args.root.resolve(), status(args.root.resolve()))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Research task readiness / 科研任务就绪状态")
        print("File presence is not completion / 文件存在不代表完成")
        zh = args.lang == "zh"
        for task in report["tasks"]:
            state = ({"ready": "可开始", "blocked": "前置条件未满足"}[task["state"]] if zh else task["state"])
            print(f"[{state}] {task['id']}: {task['title_' + args.lang]}")
            print(f"  {'负责人' if zh else 'owner'}={task['owner']}; {'复核者' if zh else 'reviewer'}={task['reviewer']}")
            for blocker in task["blockers"]:
                print("  - " + (blocker.replace("requires verified", "需要已校验门控").replace("governance ledger is invalid or unverified", "治理账本无效或未校验") if zh else blocker))
            if task["missing_implementation"]:
                print(("  待实现：" if zh else "  implementation needed: ") + ", ".join(task["missing_implementation"]))
            print(("  验收：" if zh else "  acceptance: ") + "; ".join(task["acceptance_zh" if zh else "acceptance"]))
    return 0 if report["ledger_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
