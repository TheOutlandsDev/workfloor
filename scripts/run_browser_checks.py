"""Run the synthetic browser checks using checkout-local temporary state."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-browser", action="store_true", help="Install the pinned Playwright Chromium build first")
    parser.add_argument("--pattern", default="test_*.py", help="unittest filename pattern for focused local checks")
    args = parser.parse_args()
    temporary = ROOT / ".test-tmp" / "browser-temp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "TEMP": str(temporary), "TMP": str(temporary),
                   "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / ".test-tmp" / "playwright-browsers")}
    if args.install_browser:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], cwd=ROOT, env=environment, check=True)
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "e2e", "-p", args.pattern, "-v"],
                            cwd=ROOT, env=environment)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
