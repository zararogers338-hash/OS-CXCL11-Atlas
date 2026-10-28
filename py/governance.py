"""Repository entry point; canonical governance implementation lives in the skill."""
from pathlib import Path
import runpy


if __name__ == "__main__":
    module = Path(__file__).resolve().parents[1] / "ai" / "skills" / "cxcl11-osteosarcoma-tme" / "scripts" / "governance.py"
    runpy.run_path(str(module), run_name="__main__")
