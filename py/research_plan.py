"""Run the portable skill's research readiness planner."""
import runpy
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "ai/skills/cxcl11-osteosarcoma-tme/scripts"
if __name__ == "__main__":
    sys.path.insert(0, str(SCRIPTS))
    runpy.run_path(str(SCRIPTS / "research_plan.py"), run_name="__main__")
