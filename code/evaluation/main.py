"""Evaluation workflow entry point: calibration sweep, then output validation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibrate
import validate


def main() -> int:
    print("=== calibration against solved samples ===")
    calibrate.main()
    print("\n=== output.csv validation ===")
    return 0 if validate.validate() else 1


if __name__ == "__main__":
    sys.exit(main())