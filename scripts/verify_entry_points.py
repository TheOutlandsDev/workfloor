"""Exercise the real CLI and Windows batch launcher with disposable databases.

Run from any directory: python scripts/verify_entry_points.py
Requires Python 3.12+. Windows also checks the batch launcher.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_METRICS = {
    "orders": 9, "units": 365, "delayed": 4, "completed_late": 1,
    "open_overdue": 3, "on_time": 3, "review": 2,
}


def check_entry_point(label, command, directory, *, batch=False):
    data = directory / f"{label} fresh data"
    database = data / "workfloor.sqlite3"
    if data.exists():
        raise RuntimeError(f"{label}: expected a fresh data directory")
    # shell=True is intentional for the Windows .cmd entry point. Every argument
    # comes from this script or its own temporary directory, never user input.
    process = subprocess.run(
        [*command, "--demo-report", "--data-dir", str(data)],
        cwd=directory, shell=batch, capture_output=True, text=True, timeout=30,
    )
    if process.returncode:
        raise RuntimeError(f"{label}: exit {process.returncode}\n{process.stderr}\n{process.stdout}")
    report = json.loads(process.stdout)
    validation = report["validation"]
    if not database.is_file():
        raise RuntimeError(f"{label}: database was not created in the requested directory")
    if report["metrics"] != EXPECTED_METRICS:
        raise RuntimeError(f"{label}: unexpected metrics: {report['metrics']}")
    if report["synthetic"] is not True or (report["start"], report["end"]) != ("2026-10-01", "2026-10-08"):
        raise RuntimeError(f"{label}: unexpected dataset or date range")
    if validation["correct_matches_reference"] is not True:
        raise RuntimeError(f"{label}: report disagrees with independent reference")
    if (validation["naive_orders"], validation["naive_units"], validation["extra_joined_rows"]) != (26, 1195, 17):
        raise RuntimeError(f"{label}: expected the deliberate 26-versus-9 join error")
    if validation["inflation_detected"] is not True:
        raise RuntimeError(f"{label}: deliberate join error was not detected")
    print(f"PASS {label}: fresh database; 9 orders / 365 units / 4 delayed; naive join 26; reference matches")
    return report


def main():
    if sys.version_info < (3, 12):
        raise SystemExit("This entry-point check requires Python 3.12+.")
    test_root = (ROOT / ".test-tmp").resolve()
    test_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="entry points ", dir=test_root) as temporary:
        directory = Path(temporary)
        if directory.resolve().parent != test_root:
            raise RuntimeError("Temporary directory escaped the checkout-local test root")
        cli = check_entry_point("CLI", [sys.executable, str(ROOT / "app.py")], directory)
        if os.name == 'nt':
            launcher = check_entry_point("Windows launcher", [str(ROOT / "start-workfloor.cmd")], directory, batch=True)
            if cli != launcher: raise RuntimeError("CLI and Windows launcher reports differ")
            print("PASS both entry points produced identical reports from separate databases, outside the project working directory")


if __name__ == "__main__":
    main()
