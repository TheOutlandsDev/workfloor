"""Compatibility entry point for the qualified multi-platform publisher."""
import argparse
from pathlib import Path
from release_evidence import publish

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    args = parser.parse_args()
    publish(args.artifacts, args.run_id)
