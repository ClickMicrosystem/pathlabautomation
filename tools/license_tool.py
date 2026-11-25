"""Compatibility entrypoint for the vendor license utility."""
from pathlib import Path
import runpy


if __name__ == "__main__":
    issuer = Path(__file__).resolve().parents[1] / "LicencingUtility" / "license_tool.py"
    runpy.run_path(str(issuer), run_name="__main__")
