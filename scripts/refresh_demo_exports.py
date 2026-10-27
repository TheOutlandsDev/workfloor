"""Freeze only verified synthetic browser downloads into the read-only demo."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path, help="A passed csv-workflow browser-artifact directory")
    args = parser.parse_args()
    run = args.run_directory.resolve()
    if not run.is_relative_to((ROOT / ".test-tmp" / "browser-artifacts").resolve()):
        raise SystemExit("Choose an artifact directory inside this checkout's browser-artifacts folder.")
    evidence = json.loads((run / "verification.json").read_text(encoding="utf-8"))
    if evidence.get("status") != "passed" or evidence.get("case") != "csv-workflow" or not evidence.get("receipt_bytes_verified") or not evidence.get("earlier_export_byte_identical"):
        raise SystemExit("This is not a completed, verified synthetic workflow capture.")
    for name, expected in evidence["exports"].items():
        if name not in ("baseline.json", "after-import.json", "receipt.json") or sha((run / name).read_bytes()) != expected:
            raise SystemExit("A downloaded export changed after verification.")
    for name, expected in evidence["runtime_files"].items():
        current = (ROOT / name).read_bytes()
        released = subprocess.check_output(["git", "show", "v0.2.0:" + name], cwd=ROOT)
        if sha(current) != expected or current != released:
            raise SystemExit("The tested runtime does not match the v0.2.0 source: " + name)
    source_sha = subprocess.check_output(["git", "rev-parse", "v0.2.0^{commit}"], cwd=ROOT, text=True).strip()
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf-8"))
    if receipt["csv_sha256"] != sha((ROOT / "examples/import-valid.csv").read_bytes()):
        raise SystemExit("The receipt does not match the published synthetic CSV.")
    destination = ROOT / "demo" / "data"
    destination.mkdir(parents=True, exist_ok=True)
    for name in evidence["exports"]:
        shutil.copyfile(run / name, destination / name)
    provenance = {
        "format_version": 1, "synthetic_only": True,
        "description": "Actual browser-downloaded frozen exports from the verified local Workfloor workflow. Read-only browser adaptation; no SQL runs in the viewer.",
        "captured_at": evidence["finished_at"],
        "runtime_version": "0.2.0", "runtime_ref": "v0.2.0", "runtime_commit": source_sha,
        "runtime_source": "https://github.com/TheOutlandsDev/workfloor/tree/v0.2.0",
        "csv_source": "https://github.com/TheOutlandsDev/workfloor/blob/v0.2.0/examples/import-valid.csv",
        "csv_sha256": receipt["csv_sha256"], "files": evidence["exports"],
        "browser": evidence["chromium"], "python": evidence["python"], "sqlite": evidence["sqlite"],
        "platform": evidence["platform"], "runtime_files": evidence["runtime_files"],
        "checks": {"receipt_download_verified": True, "earlier_export_byte_identical_after_reload": True},
    }
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print("Frozen three verified synthetic downloads and their provenance in demo/data")


if __name__ == "__main__":
    main()
