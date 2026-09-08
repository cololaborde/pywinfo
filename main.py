#!/usr/bin/env python3

import os
import sys
from pathlib import Path

try:
    import pytest
except ImportError:
    print(
        "pytest no está instalado. Instalalo con: "
        "pip install -e '.[test]'"
    )
    sys.exit(1)

from src.__main__ import main as run_dashboard

ROOT = Path(__file__).resolve().parent


def run_tests():
    print("Corriendo tests antes de generar el dashboard...")

    # -q: salida resumida. La config (testpaths, pythonpath) la
    # lee pytest del pyproject.toml del rootdir.
    return pytest.main(["-q"])


def main():
    os.chdir(ROOT)

    exit_code = run_tests()

    if exit_code != 0:
        print("\nLos tests fallaron; no se genera el dashboard.")
        sys.exit(exit_code)

    run_dashboard()


if __name__ == "__main__":
    main()