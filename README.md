# pywinfo

Self-contained HTML dashboard with detailed Linux hardware information. Runs system commands (`hwinfo`, `lsblk`, `lscpu`, `dmidecode`, `ip`, `/proc/*`) to auto-detect CPU, GPU, RAM, disks, network, monitors, USB, audio, Bluetooth, cameras, and BIOS/system info, then opens the result in your browser.

## Features

- **Automatic hardware detection** via `hwinfo`, `lsblk`, `lscpu`, `dmidecode`, `ip`, and `/proc` files
- **Smart data sourcing** — uses the most precise tool per category (`lsblk -b` for exact byte sizes, `lscpu -J` for CPU topology, `dmidecode` for RAM module detail, `ip -j` for live NIC state) with `hwinfo` as a rich fallback
- **Auto-install `hwinfo`** — detects your package manager (`dnf`, `apt`, `pacman`, `zypper`) and installs it via `sudo` if missing
- **Self-contained HTML report** — single file with inlined CSS, JS, and embedded JSON data; dark-themed UI with sidebar navigation
- **Chart.js bar charts** — CPU frequency per logical core, storage sizes (requires internet for CDN)
- **Test gate** — `main.py` runs the test suite before generating the dashboard

## Requirements

- Python >= 3.8
- Linux with at least one of: `dnf`, `apt`, `pacman`, `zypper`
- System tools (most bundled, `hwinfo` auto-installed):
  - `hwinfo` (auto-installed)
  - `lsblk` (util-linux)
  - `lscpu` (util-linux)
  - `dmidecode`
  - `ip` (iproute2)

## Installation

```bash
# Editable install (recommended for development)
pip install -e .

# With test dependencies
pip install -e '.[test]'

# Or just install pytest for tests
pip install -r requirements.txt
```

## Usage

```bash
# Console script (after pip install)
hwinfo-dashboard

# As a module
python -m src

# Via the test-gated launcher (runs pytest first)
python main.py
```

On execution:

1. Installs `hwinfo` if not present
2. Prompts for `sudo` (needed for BIOS/DMI and full hardware detail)
3. Gathers and parses hardware data
4. Generates `hwinfo_dashboard.html` in your temp directory
5. Opens it in the default browser

## Project Structure

```
pywinfo/
├── main.py                     # Test-gated launcher
├── pyproject.toml              # Package config (setuptools)
├── requirements.txt            # pytest
├── src/
│   ├── __init__.py             # __version__ = "0.1.0"
│   ├── __main__.py             # CLI entry point
│   ├── data.py                 # Unified data assembly
│   ├── hwinfo_parser.py        # hwinfo block/short parsing
│   ├── system.py               # Command runner, hwinfo installer
│   ├── utils.py                # Text/byte parsing helpers
│   ├── collectors/             # Per-category data collectors
│   │   ├── audio.py
│   │   ├── bios.py
│   │   ├── bluetooth.py
│   │   ├── cameras.py
│   │   ├── cpu.py
│   │   ├── disks.py
│   │   ├── gpu.py
│   │   ├── memory.py
│   │   ├── monitors.py
│   │   ├── network.py
│   │   └── usb.py
│   └── report/                 # HTML report generation
│       ├── generator.py
│       ├── template.html
│       └── assets/
│           ├── app.js
│           └── style.css
└── tests/
    ├── conftest.py
    ├── fixtures/               # Sample hwinfo/lsblk/lscpu/dmidecode output
    ├── test_cpu.py
    ├── test_disks.py
    └── test_network.py
```

## Running Tests

```bash
pytest -q
```

## License

MIT
