import re

from src.system import command_exists, run_command
from src.utils import normalize_key


def clean_dmidecode_value(value):
    if not value:
        return None

    value = value.strip()

    if value.lower() in ("not specified", "unknown", "no module installed", ""):
        return None

    return value


def get_dmidecode_memory():
    """
    hwinfo no reporta el detalle por módulo (slot, tipo DDR4/DDR5,
    velocidad, fabricante). Para eso la fuente correcta es la tabla
    SMBIOS/DMI vía `dmidecode -t memory` (requiere root).
    """

    if not command_exists("dmidecode"):
        return []

    try:
        output = run_command(["dmidecode", "-t", "memory"], sudo=True)
    except Exception:
        return []

    devices = []
    current = None

    for raw_line in output.splitlines():
        stripped = raw_line.strip()

        if stripped == "Memory Device":
            if current is not None:
                devices.append(current)

            current = {}
            continue

        if current is None:
            continue

        if not stripped:
            devices.append(current)
            current = None
            continue

        if ":" not in stripped:
            continue

        key, _, value = stripped.partition(":")
        current[normalize_key(key)] = value.strip()

    if current is not None:
        devices.append(current)

    modules = []

    for device in devices:
        size_raw = device.get("size", "")

        if not size_raw or "no module installed" in size_raw.lower():
            # Slot vacío, no es un módulo instalado.
            continue

        modules.append(
            {
                "locator": clean_dmidecode_value(device.get("locator")),
                "bank_locator": clean_dmidecode_value(
                    device.get("bank_locator")
                ),
                "size": size_raw.strip(),
                "type": clean_dmidecode_value(device.get("type")),
                "speed": clean_dmidecode_value(device.get("speed")),
                "configured_speed": clean_dmidecode_value(
                    device.get("configured_memory_speed")
                ),
                "manufacturer": clean_dmidecode_value(
                    device.get("manufacturer")
                ),
                "part_number": clean_dmidecode_value(
                    device.get("part_number")
                ),
            }
        )

    return modules


def get_system_memory():
    """
    hwinfo suele decir solamente "Main Memory". Para el tamaño total
    usamos /proc/meminfo (el kernel, no hwinfo), y para el detalle
    por módulo físico usamos dmidecode.
    """

    total_kb = None

    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(
                        re.search(r"\d+", line).group()
                    )
                    break
    except Exception:
        pass

    total_bytes = (total_kb * 1024) if total_kb else 0

    modules = get_dmidecode_memory()

    return {
        "total_bytes": total_bytes,
        "total_gb": (
            round(total_bytes / (1024 ** 3), 2) if total_bytes else 0
        ),
        "modules": modules,
    }