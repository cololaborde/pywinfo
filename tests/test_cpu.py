import json
from unittest import mock

from src.hwinfo_parser import (
    parse_hwinfo_blocks,
    parse_hwinfo_short,
)
from src.collectors import cpu


@mock.patch("src.collectors.cpu.run_command")
@mock.patch(
    "src.collectors.cpu.command_exists", return_value=True
)
def test_get_lscpu_normalizes_json(mock_command_exists, mock_run, lscpu_sample):
    mock_run.return_value = json.dumps(lscpu_sample)

    result = cpu.get_lscpu()

    assert result["Architecture"] == "x86_64"
    assert result["CPU(s)"] == 8
    assert result["Model name"] == "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz"
    assert result["Socket(s)"] == 1
    assert result["Core(s) per socket"] == 4
    assert result["Thread(s) per core"] == 2
    assert result["CPU max MHz"] == "4000.0000"
    assert result["L3 cache"] == "8 MiB"


@mock.patch(
    "src.collectors.cpu.get_proc_cpuinfo_frequencies",
    return_value=[],
)
def test_parse_cpu_prefers_lscpu(mock_frequencies):
    lscpu = {
        "Architecture": "x86_64",
        "CPU(s)": 8,
        "Vendor ID": "GenuineIntel",
        "Model name": "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz",
        "Socket(s)": 1,
        "Core(s) per socket": 4,
        "Thread(s) per core": 2,
        "CPU max MHz": "4000.0000",
        "CPU min MHz": "400.0000",
        "L1d cache": "128 KiB",
        "L3 cache": "8 MiB",
        "Virtualization": "VT-x",
    }

    with mock.patch(
        "src.collectors.cpu.get_lscpu", return_value=lscpu
    ):
        result = cpu.parse_cpu([], {})

    assert result["model"] == "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz"
    assert result["vendor"] == "GenuineIntel"
    assert result["architecture"] == "x86_64"
    assert result["sockets"] == 1
    assert result["physical_cores"] == 4
    assert result["threads_per_core"] == 2
    assert result["logical_processors"] == 8
    assert result["max_mhz"] == 4000.0
    assert result["min_mhz"] == 400.0
    assert result["cache"]["l3"] == "8 MiB"
    assert result["virtualization"] == "VT-x"


@mock.patch("src.collectors.cpu.get_proc_cpuinfo_frequencies")
@mock.patch(
    "src.collectors.cpu.get_proc_cpuinfo_summary"
)
@mock.patch(
    "src.collectors.cpu.get_lscpu", return_value=None
)
def test_parse_cpu_falls_back_to_proc_cpuinfo(
    mock_lscpu, mock_summary, mock_frequencies
):
    mock_summary.return_value = {
        "model": "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz",
        "vendor": "GenuineIntel",
        "architecture": None,
        "sockets": 1,
        "physical_cores": 4,
        "threads_per_core": None,
        "logical_processors": 8,
        "max_mhz": None,
        "min_mhz": None,
        "cache": {},
        "virtualization": None,
        "frequencies": [],
    }
    mock_frequencies.return_value = [1797.0, 1797.0]

    result = cpu.parse_cpu([], {})

    assert result["model"] == "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz"
    assert result["sockets"] == 1
    assert result["physical_cores"] == 4
    assert result["logical_processors"] == 8
    assert result["frequencies"] == [1797.0, 1797.0]


@mock.patch(
    "src.collectors.cpu.get_proc_cpuinfo_frequencies",
    return_value=[],
)
@mock.patch(
    "src.collectors.cpu.get_proc_cpuinfo_summary",
    return_value=None,
)
@mock.patch(
    "src.collectors.cpu.get_lscpu", return_value=None
)
def test_parse_cpu_falls_back_to_hwinfo_blocks(
    mock_lscpu, mock_summary, mock_frequencies, hwinfo_sample
):
    blocks = parse_hwinfo_blocks(hwinfo_sample)

    result = cpu.parse_cpu(blocks, {})

    assert result["model"] == "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz"
    assert result["vendor"] == "Intel Corporation"
    assert result["logical_processors"] == 1


@mock.patch(
    "src.collectors.cpu.get_proc_cpuinfo_frequencies",
    return_value=[],
)
@mock.patch(
    "src.collectors.cpu.get_proc_cpuinfo_summary",
    return_value=None,
)
@mock.patch(
    "src.collectors.cpu.get_lscpu", return_value=None
)
def test_parse_cpu_falls_back_to_short(
    mock_lscpu, mock_summary, mock_frequencies
):
    short = parse_hwinfo_short(
        "cpu:\n"
        "  Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz\n"
        "  Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz\n"
    )

    result = cpu.parse_cpu([], short)

    assert result["model"] == "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz"
    assert result["logical_processors"] == 2