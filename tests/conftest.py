import json
import sys
from pathlib import Path

import pytest

# Asegura que el paquete sea importable sin instalarlo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def hwinfo_sample():
    return (FIXTURES / "hwinfo_sample.txt").read_text(encoding="utf-8")


@pytest.fixture
def lsblk_sample():
    return json.loads(
        (FIXTURES / "lsblk_sample.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def lscpu_sample():
    return json.loads(
        (FIXTURES / "lscpu_sample.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def dmidecode_memory_sample():
    return (FIXTURES / "dmidecode_memory_sample.txt").read_text(
        encoding="utf-8"
    )