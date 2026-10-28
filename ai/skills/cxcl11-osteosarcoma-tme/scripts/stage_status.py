"""Read-only gate board: verified state and historical decisions are separate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from governance import status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("--lang", choices=["en", "zh"], default="en")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = status(args.root)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ledger_valid"] else 2
    zh = args.lang == "zh"
    labels = {"ready": "待提交证据", "proposed": "待独立审核", "passed": "机器验证通过",
              "rejected": "审核未通过", "revoked": "已撤销", "stale": "证据或绑定已变更",
              "blocked": "前置门控未通过", "invalid": "治理验证失败"}
    print("OS-CXCL11 Atlas 门控进度" if zh else "OS-CXCL11 Atlas gate progress")
    print(("账本结构有效" if report["ledger_valid"] else "账本或配置无效") if zh else
          ("Ledger structurally valid" if report["ledger_valid"] else "Ledger/configuration invalid"))
    for gate in report["gates"]:
        print(f"{gate['id']}: {labels[gate['status']] if zh else gate['status']}")
        if gate.get("historical_decision"):
            print(("  历史记录（不等于机器验证）: " if zh else "  Historical (not machine-verified): ") + gate["historical_decision"])
        for blocker in gate["blockers"]:
            print("  - " + blocker)
    print("历史决策保留；新协议不会自动认定通过。哈希不验证科学结论或真实身份。" if zh else
          "Historical decisions are preserved. Hashes validate neither scientific conclusions nor actor identity.")
    return 0 if report["ledger_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
