#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import tempfile
import webbrowser
from pathlib import Path


# ============================================================
# COMMANDS
# ============================================================

def command_exists(command):
    return shutil.which(command) is not None


def install_hwinfo():
    if command_exists("hwinfo"):
        return

    print("hwinfo no está instalado. Intentando instalarlo...")

    commands = []

    if command_exists("dnf"):
        commands = [
            ["sudo", "dnf", "install", "-y", "hwinfo"],
        ]
    elif command_exists("apt"):
        commands = [
            ["sudo", "apt", "update"],
            ["sudo", "apt", "install", "-y", "hwinfo"],
        ]
    elif command_exists("pacman"):
        commands = [
            ["sudo", "pacman", "-Sy", "--noconfirm", "hwinfo"],
        ]
    elif command_exists("zypper"):
        commands = [
            ["sudo", "zypper", "--non-interactive", "install", "hwinfo"],
        ]

    if not commands:
        raise RuntimeError(
            "No encontré un gestor de paquetes compatible "
            "(dnf, apt, pacman o zypper)."
        )

    for command in commands:
        subprocess.run(command, check=True)

    if not command_exists("hwinfo"):
        raise RuntimeError("No se pudo instalar hwinfo.")


def run_command(command, sudo=False):
    if sudo:
        command = ["sudo"] + command

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Error ejecutando {' '.join(command)}:\n{result.stderr}"
        )

    return result.stdout


def get_hwinfo():
    install_hwinfo()

    # Sin root, hwinfo omite bastante información (BIOS/DMI, algunos
    # recursos de bus, etc). Lo corremos con sudo para tener el detalle
    # completo.
    print("Obteniendo información detallada de hardware (sudo)...")
    detailed = run_command(["hwinfo"], sudo=True)

    print("Obteniendo resumen...")
    short = run_command(["hwinfo", "--short"], sudo=True)

    return detailed, short


# ============================================================
# GENERIC HELPERS
# ============================================================

def clean_value(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Quitar comillas exteriores
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]

    value = value.strip()

    return value or None


def parse_value(value):
    """
    Convierte:

        "Intel Corporation"
        1234
        cfg=new, avail=yes

    en valores limpios.
    """

    value = clean_value(value)

    if value is None:
        return None

    # No intentamos convertir agresivamente números porque
    # hwinfo utiliza muchos identificadores hexadecimales.
    return value


def normalize_key(key):
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def normalize_bool(value):
    """
    Convierte valores típicos de lsblk (bool nativo, "0"/"1",
    "yes"/"no") a True/False/None.
    """

    if isinstance(value, bool):
        return value

    if value is None:
        return None

    value = str(value).strip().lower()

    if value in ("1", "yes", "true"):
        return True

    if value in ("0", "no", "false"):
        return False

    return None


def safe_int(value):
    try:
        if value is None:
            return None

        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value):
    try:
        if value is None:
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def format_bytes(size_bytes):
    """
    Convierte un tamaño en bytes a una representación legible,
    p.ej. 500107862016 -> "465.8 GB".
    """

    if not size_bytes:
        return None

    size = float(size_bytes)

    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(size)} {unit}"

            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{size:.1f} PB"


def first_value(data, *keys):
    """
    Busca la primera clave disponible.
    """

    for key in keys:
        normalized = normalize_key(key)

        if normalized in data:
            value = data[normalized]

            if isinstance(value, list):
                if value:
                    return value[0]
            elif value:
                return value

    return None


def all_values(data, *keys):
    result = []

    for key in keys:
        normalized = normalize_key(key)

        value = data.get(normalized)

        if value is None:
            continue

        if isinstance(value, list):
            result.extend(value)
        else:
            result.append(value)

    return result


# ============================================================
# HWINFO DETAILED PARSER
# ============================================================

BLOCK_START_RE = re.compile(
    r"^\s*(\d{2}):\s+(.+?)\s*$"
)

PROPERTY_RE = re.compile(
    r"^\s{2,}([^:]+):\s*(.*?)\s*$"
)


def parse_config_status(value):
    result = {}

    if not value:
        return result

    for item in value.split(","):
        item = item.strip()

        if "=" not in item:
            continue

        key, val = item.split("=", 1)

        result[key.strip()] = val.strip()

    return result


def parse_hwinfo_blocks(text):
    """
    Parseo de la salida completa de hwinfo.

    Un bloque normalmente empieza así:

        01: None 00.0: 10105 BIOS
          Model: "..."
          Vendor: "..."
          Hardware Class: bios
          ...

    No dependemos de que las propiedades estén en un orden concreto.
    """

    blocks = []
    current = None

    for line in text.splitlines():
        match = BLOCK_START_RE.match(line)

        if match:
            if current:
                blocks.append(current)

            current = {
                "id": match.group(1),
                "header": match.group(2).strip(),
                "properties": {},
            }

            continue

        if current is None:
            continue

        prop_match = PROPERTY_RE.match(line)

        if not prop_match:
            continue

        key = normalize_key(prop_match.group(1))
        value = parse_value(prop_match.group(2))

        if not value:
            continue

        # Algunas propiedades pueden repetirse
        if key in current["properties"]:
            existing = current["properties"][key]

            if not isinstance(existing, list):
                existing = [existing]

            existing.append(value)
            current["properties"][key] = existing
        else:
            current["properties"][key] = value

    if current:
        blocks.append(current)

    # Hardware class a nivel superior
    for block in blocks:
        props = block["properties"]

        hardware_class = first_value(
            props,
            "hardware_class",
        )

        block["class"] = (
            hardware_class.lower()
            if hardware_class
            else detect_class_from_header(block["header"])
        )

    return blocks


def detect_class_from_header(header):
    header_lower = header.lower()

    mapping = [
        ("bios", "bios"),
        ("processor", "cpu"),
        ("cpu", "cpu"),
        ("memory", "memory"),
        ("disk", "disk"),
        ("storage", "storage"),
        ("network", "network"),
        ("ethernet", "network"),
        ("wireless", "network"),
        ("monitor", "monitor"),
        ("graphics", "graphics"),
        ("video", "graphics"),
        ("sound", "sound"),
        ("audio", "sound"),
        ("usb", "usb"),
        ("bluetooth", "bluetooth"),
        ("keyboard", "keyboard"),
        ("mouse", "mouse"),
        ("camera", "camera"),
        ("webcam", "camera"),
    ]

    for pattern, result in mapping:
        if pattern in header_lower:
            return result

    return "unknown"


# ============================================================
# SHORT OUTPUT PARSER
# ============================================================

SHORT_SECTION_RE = re.compile(
    r"^([a-zA-Z0-9 _-]+):\s*$"
)

SHORT_DEVICE_RE = re.compile(
    r"^\s{2,}(.+?)\s*$"
)


def parse_hwinfo_short(text):
    """
    Convierte:

        cpu:
          Intel(...)
          Intel(...)

        graphics card:
          Intel VGA compatible controller

    en:

        {
            "cpu": [...],
            "graphics_card": [...]
        }
    """

    result = {}
    current_section = None

    for line in text.splitlines():
        section_match = SHORT_SECTION_RE.match(line)

        if section_match:
            current_section = normalize_key(section_match.group(1))

            result.setdefault(current_section, [])

            continue

        if current_section is None:
            continue

        if not line.strip():
            continue

        value = line.strip()

        result[current_section].append(value)

    return result


# ============================================================
# CATEGORY HELPERS
# ============================================================

def block_matches(block, keywords):
    text = " ".join(
        [
            block.get("header", ""),
            block.get("class", ""),
            json.dumps(block.get("properties", {})),
        ]
    ).lower()

    return any(keyword.lower() in text for keyword in keywords)


def get_blocks(blocks, classes=None, keywords=None):
    classes = classes or []
    keywords = keywords or []

    result = []

    for block in blocks:
        if classes and block.get("class") in classes:
            result.append(block)
            continue

        if keywords and block_matches(block, keywords):
            result.append(block)

    return result


def block_label(block):
    props = block["properties"]

    return (
        first_value(
            props,
            "model",
            "device",
            "vendor",
        )
        or block.get("header")
        or "Dispositivo"
    )


def block_vendor(block):
    return first_value(
        block["properties"],
        "vendor",
        "sub_vendor",
    )


def block_driver(block):
    return first_value(
        block["properties"],
        "driver",
        "driver_modules",
    )


# ============================================================
# CPU
# ============================================================

def get_lscpu():
    """
    lscpu -J es la fuente correcta para topología de CPU: sockets,
    cores físicos vs hilos, cache por nivel, MHz min/max reales.
    hwinfo reporta un bloque por CPU lógica y su "Clock" no siempre
    refleja el turbo/min real, así que lo dejamos solo como último
    fallback más abajo.
    """

    if not command_exists("lscpu"):
        return None

    try:
        output = run_command(["lscpu", "-J"])
        data = json.loads(output)
    except Exception:
        return None

    result = {}

    def walk(items):
        for item in items or []:
            field = (item.get("field") or "").rstrip(":").strip()

            if field:
                result[field] = item.get("data")

            walk(item.get("children"))

    walk(data.get("lscpu", []))

    return result or None


def get_proc_cpuinfo_frequencies():
    """
    Frecuencias actuales por núcleo lógico, en tiempo real, leídas
    directamente del kernel en vez de un valor estático de hwinfo.
    """

    frequencies = []

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("cpu mhz"):
                    match = re.search(r"([\d.]+)", line)

                    if match:
                        frequencies.append(float(match.group(1)))
    except Exception:
        pass

    return frequencies


def get_proc_cpuinfo_summary():
    """
    Fallback cuando no hay lscpu: reconstruye modelo, sockets y
    cores físicos a partir de /proc/cpuinfo (physical id / core id).
    """

    try:
        with open("/proc/cpuinfo") as f:
            content = f.read()
    except Exception:
        return None

    model = None
    vendor = None
    logical = 0
    physical_ids = set()
    core_ids = set()

    for entry in content.split("\n\n"):
        fields = {}

        for line in entry.splitlines():
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()

        if "processor" not in fields:
            continue

        logical += 1

        if model is None:
            model = fields.get("model name")

        if vendor is None:
            vendor = fields.get("vendor_id")

        if "physical id" in fields and "core id" in fields:
            physical_ids.add(fields["physical id"])
            core_ids.add((fields["physical id"], fields["core id"]))

    if logical == 0:
        return None

    return {
        "model": model,
        "vendor": vendor,
        "architecture": None,
        "sockets": len(physical_ids) or None,
        "physical_cores": len(core_ids) or None,
        "threads_per_core": None,
        "logical_processors": logical,
        "max_mhz": None,
        "min_mhz": None,
        "cache": {},
        "virtualization": None,
        "frequencies": [],
    }


def parse_cpu(blocks, short):
    frequencies = get_proc_cpuinfo_frequencies()

    # --- Fuente primaria: lscpu -J ---
    lscpu = get_lscpu()

    if lscpu:
        sockets = safe_int(lscpu.get("Socket(s)"))
        cores_per_socket = safe_int(lscpu.get("Core(s) per socket"))
        threads_per_core = safe_int(lscpu.get("Thread(s) per core"))
        logical = safe_int(lscpu.get("CPU(s)"))

        physical_cores = (
            sockets * cores_per_socket
            if sockets and cores_per_socket
            else None
        )

        return {
            "model": lscpu.get("Model name") or lscpu.get("Model"),
            "vendor": lscpu.get("Vendor ID"),
            "architecture": lscpu.get("Architecture"),
            "sockets": sockets,
            "physical_cores": physical_cores,
            "threads_per_core": threads_per_core,
            "logical_processors": logical or (len(frequencies) or None),
            "max_mhz": safe_float(lscpu.get("CPU max MHz")),
            "min_mhz": safe_float(lscpu.get("CPU min MHz")),
            "cache": {
                "l1d": lscpu.get("L1d cache"),
                "l1i": lscpu.get("L1i cache"),
                "l2": lscpu.get("L2 cache"),
                "l3": lscpu.get("L3 cache"),
            },
            "virtualization": lscpu.get("Virtualization"),
            "frequencies": frequencies,
        }

    # --- Fallback: /proc/cpuinfo ---
    proc_summary = get_proc_cpuinfo_summary()

    if proc_summary:
        proc_summary["frequencies"] = (
            frequencies or proc_summary["frequencies"]
        )
        return proc_summary

    # --- Último fallback: hwinfo (menos confiable para clocks/cache) ---
    cpu_blocks = get_blocks(
        blocks,
        classes=["cpu", "processor"],
        keywords=[
            "processor",
            "cpu",
            "core",
            "intel(r)",
            "amd",
        ],
    )

    cpus = []

    for block in cpu_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
            "processor",
        )

        vendor = first_value(
            props,
            "vendor",
        )

        clock = first_value(
            props,
            "clock",
            "current_clock",
            "frequency",
        )

        if not model:
            continue

        cpus.append(
            {
                "model": model,
                "vendor": vendor,
                "clock": clock,
            }
        )

    def empty_result(model=None, vendor=None, logical=0, freqs=None):
        return {
            "model": model,
            "vendor": vendor,
            "architecture": None,
            "sockets": None,
            "physical_cores": None,
            "threads_per_core": None,
            "logical_processors": logical,
            "max_mhz": None,
            "min_mhz": None,
            "cache": {},
            "virtualization": None,
            "frequencies": freqs or [],
        }

    if cpus:
        model_counts = {}

        for cpu in cpus:
            key = cpu["model"]
            model_counts[key] = model_counts.get(key, 0) + 1

        main_model = max(model_counts, key=model_counts.get)

        hwinfo_freqs = [cpu["clock"] for cpu in cpus if cpu["clock"]]

        return empty_result(
            model=main_model,
            vendor=cpus[0].get("vendor"),
            logical=len(cpus),
            freqs=hwinfo_freqs,
        )

    # Fallback al short
    short_cpus = short.get("cpu", [])

    if short_cpus:
        models = []

        for value in short_cpus:
            model = re.sub(
                r",\s*[\d.]+\s*MHz.*$",
                "",
                value,
                flags=re.IGNORECASE,
            ).strip()

            if model:
                models.append(model)

        if models:
            counts = {}

            for model in models:
                counts[model] = counts.get(model, 0) + 1

            return empty_result(
                model=max(counts, key=counts.get),
                logical=len(models),
                freqs=short_cpus,
            )

    return empty_result()


# ============================================================
# MEMORY
# ============================================================

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


# ============================================================
# GPU
# ============================================================

def parse_gpu(blocks, short):
    gpu_blocks = get_blocks(
        blocks,
        classes=["graphics", "display"],
        keywords=[
            "graphics",
            "vga",
            "display controller",
        ],
    )

    gpus = []

    for block in gpu_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
        )

        vendor = first_value(
            props,
            "vendor",
        )

        driver = block_driver(block)

        bus_id = first_value(
            props,
            "sysfs_busid",
            "sysfs_id",
        )

        if model or vendor:
            gpus.append(
                {
                    "model": model or "GPU",
                    "vendor": vendor,
                    "driver": driver,
                    "bus_id": bus_id,
                }
            )

    if gpus:
        return gpus

    short_gpus = short.get("graphics_card", [])

    return [
        {
            "model": value,
            "vendor": None,
            "driver": None,
            "bus_id": None,
        }
        for value in short_gpus
    ]


# ============================================================
# DISKS
# ============================================================
#
# Importante: el tamaño (y en general la info "real" de bloque)
# NO se saca de hwinfo. hwinfo describe el hardware detectado por
# bus/PCI/USB, pero para tamaños, particiones, filesystem, punto de
# montaje, tipo de disco (rotacional/SSD/NVMe), serial, etc. la
# fuente correcta es el kernel a través de lsblk. Por eso pedimos
# los tamaños en bytes exactos con `-b` y evitamos parsear strings
# del estilo "500G" con regex.

# Distintas versiones de util-linux soportan distintas columnas de
# lsblk (p.ej. TRAN, SERIAL o PTTYPE no siempre están disponibles).
# Probamos de la más completa a la más básica para no romper en
# sistemas viejos.
LSBLK_COLUMN_SETS = [
    "NAME,KNAME,TYPE,SIZE,MODEL,VENDOR,SERIAL,FSTYPE,MOUNTPOINT,ROTA,TRAN,RM,PTTYPE",
    "NAME,KNAME,TYPE,SIZE,MODEL,VENDOR,SERIAL,FSTYPE,MOUNTPOINT,ROTA,TRAN,RM",
    "NAME,KNAME,TYPE,SIZE,MODEL,VENDOR,FSTYPE,MOUNTPOINT,ROTA,TRAN",
    "NAME,KNAME,TYPE,SIZE,MODEL,VENDOR,FSTYPE,MOUNTPOINT",
]


def get_lsblk():
    if not command_exists("lsblk"):
        return []

    for columns in LSBLK_COLUMN_SETS:
        try:
            # -b: tamaños en bytes exactos (nada de "500G" para parsear).
            # -J: salida JSON, mucho más robusta que parsear texto tabular.
            output = run_command(
                ["lsblk", "-J", "-b", "-o", columns]
            )

            data = json.loads(output)

            return data.get("blockdevices", [])

        except Exception:
            continue

    return []


def disk_type_label(rotational, transport, kname):
    kname = (kname or "").lower()
    transport = (transport or "").lower()

    if "nvme" in kname or transport == "nvme":
        return "NVMe SSD"

    if rotational is True:
        return "HDD"

    if rotational is False:
        return "SSD"

    return "Desconocido"


def build_partition(node):
    size_bytes = safe_int(node.get("size"))

    kname = node.get("kname") or node.get("name")

    return {
        "device": f"/dev/{kname}" if kname else None,
        "name": node.get("name"),
        "size_bytes": size_bytes,
        "size_gb": (
            round(size_bytes / (1024 ** 3), 2)
            if size_bytes
            else None
        ),
        "size_human": format_bytes(size_bytes),
        "filesystem": clean_value(node.get("fstype")),
        "mountpoint": clean_value(node.get("mountpoint")),
    }


def build_disk(node):
    kname = node.get("kname") or node.get("name")

    size_bytes = safe_int(node.get("size"))
    rotational = normalize_bool(node.get("rota"))
    removable = normalize_bool(node.get("rm"))
    transport = clean_value(node.get("tran"))
    partition_table = clean_value(node.get("pttype"))

    partitions = [
        build_partition(child)
        for child in node.get("children", []) or []
        if child.get("type") == "part"
    ]

    return {
        "device": f"/dev/{kname}" if kname else None,
        "model": clean_value(node.get("model")) or "Disco",
        "vendor": clean_value(node.get("vendor")),
        "serial": clean_value(node.get("serial")),
        "transport": transport,
        "rotational": rotational,
        "removable": removable,
        "partition_table": partition_table,
        "type": disk_type_label(rotational, transport, kname),
        "size_bytes": size_bytes,
        "size_gb": (
            round(size_bytes / (1024 ** 3), 2)
            if size_bytes
            else None
        ),
        "size_human": format_bytes(size_bytes),
        # Solo tiene sentido si el disco no tiene tabla de
        # particiones y está formateado directamente.
        "filesystem": clean_value(node.get("fstype")),
        "mountpoint": clean_value(node.get("mountpoint")),
        "partitions": partitions,
    }


def parse_disks(blocks, short):
    lsblk_devices = get_lsblk()

    disks = [
        build_disk(node)
        for node in lsblk_devices
        if node.get("type") == "disk"
    ]

    if disks:
        return disks

    # Fallback a hwinfo solo si lsblk no está disponible.
    # OJO: en este caso NO inventamos tamaños; quedan en None
    # para que el dashboard lo muestre como "no disponible" en
    # lugar de un dato potencialmente incorrecto.
    disk_blocks = get_blocks(
        blocks,
        classes=["disk"],
        keywords=[
            "disk",
            "non-volatile memory",
            "nvme",
            "samsung",
            "storage",
        ],
    )

    for block in disk_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
        )

        device_file = first_value(
            props,
            "device_file",
            "device_files",
        )

        if not (model or device_file):
            continue

        disks.append(
            {
                "device": device_file,
                "model": model or "Disco",
                "vendor": block_vendor(block),
                "serial": None,
                "transport": None,
                "rotational": None,
                "removable": None,
                "partition_table": None,
                "type": "Desconocido",
                "size_bytes": None,
                "size_gb": None,
                "size_human": None,
                "filesystem": None,
                "mountpoint": None,
                "partitions": [],
            }
        )

    return disks


# ============================================================
# NETWORK
# ============================================================

def get_ip_addr_json():
    """
    hwinfo describe el hardware (modelo/vendor/driver de la NIC) pero
    no dice si la interfaz está arriba, qué MAC/IP tiene ni el MTU.
    Para el estado real usamos `ip -j addr`, que es lo que el kernel
    reporta en este momento.
    """

    if not command_exists("ip"):
        return []

    try:
        output = run_command(["ip", "-j", "addr"])
        return json.loads(output)
    except Exception:
        return []


def build_hw_network_map(blocks):
    """
    Mapa {interfaz: {model, vendor, driver}} a partir de hwinfo,
    cuando se puede identificar el nombre real de la interfaz dentro
    del header del bloque (p.ej. "wlo1", "enp3s0").
    """

    network_blocks = get_blocks(
        blocks,
        classes=["network"],
        keywords=[
            "ethernet",
            "wireless",
            "network",
            "wlan",
            "wifi",
        ],
    )

    hw_map = {}
    unmatched = []

    for block in network_blocks:
        props = block["properties"]

        model = first_value(props, "model", "device")
        vendor = block_vendor(block)
        driver = block_driver(block)

        if not (model or vendor):
            continue

        header = block["header"]

        interface_match = re.search(
            r"\b(wlo\d+|wlan\d+|eth\d+|en[a-z0-9]+)\b",
            header,
            re.IGNORECASE,
        )

        entry = {"model": model, "vendor": vendor, "driver": driver}

        if interface_match:
            hw_map[interface_match.group(1)] = entry
        else:
            unmatched.append(entry)

    return hw_map, unmatched


def parse_network(blocks, short):
    hw_map, unmatched_hw = build_hw_network_map(blocks)

    ip_data = get_ip_addr_json()

    interfaces = []
    seen = set()

    for item in ip_data:
        ifname = item.get("ifname")

        if not ifname or ifname == "lo":
            continue

        hw = hw_map.get(ifname, {})

        addr_info = item.get("addr_info", []) or []

        ip_addresses = [
            {
                "address": entry.get("local"),
                "prefix": entry.get("prefixlen"),
                "family": entry.get("family"),
            }
            for entry in addr_info
            if entry.get("local")
        ]

        interfaces.append(
            {
                "interface": ifname,
                "model": hw.get("model"),
                "vendor": hw.get("vendor"),
                "driver": hw.get("driver"),
                "mac": clean_value(item.get("address")),
                "state": (item.get("operstate") or "").upper() or None,
                "mtu": item.get("mtu"),
                "ip_addresses": ip_addresses,
            }
        )

        seen.add(ifname)

    # Interfaces que hwinfo detecta pero que `ip` no reporta (p.ej.
    # deshabilitadas, sin driver cargado o sin cable).
    for ifname, hw in hw_map.items():
        if ifname in seen:
            continue

        interfaces.append(
            {
                "interface": ifname,
                "model": hw.get("model"),
                "vendor": hw.get("vendor"),
                "driver": hw.get("driver"),
                "mac": None,
                "state": None,
                "mtu": None,
                "ip_addresses": [],
            }
        )

        seen.add(ifname)

    # Hardware de red sin nombre de interfaz identificado (poco común).
    for hw in unmatched_hw:
        interfaces.append(
            {
                "interface": None,
                "model": hw.get("model"),
                "vendor": hw.get("vendor"),
                "driver": hw.get("driver"),
                "mac": None,
                "state": None,
                "mtu": None,
                "ip_addresses": [],
            }
        )

    # Último fallback: ni hwinfo detallado ni `ip` dieron nada.
    if not interfaces:
        for value in short.get("network_interface", []):
            match = re.match(r"^([a-zA-Z0-9_.-]+)\s+(.+)$", value)

            if not match:
                continue

            interfaces.append(
                {
                    "interface": match.group(1),
                    "model": match.group(2),
                    "vendor": None,
                    "driver": None,
                    "mac": None,
                    "state": None,
                    "mtu": None,
                    "ip_addresses": [],
                }
            )

    return interfaces


# ============================================================
# MONITORS
# ============================================================

def parse_monitors(blocks, short):
    monitor_blocks = get_blocks(
        blocks,
        classes=["monitor"],
        keywords=[
            "monitor",
            "lcd",
            "display",
        ],
    )

    monitors = []

    for block in monitor_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
        )

        vendor = block_vendor(block)

        if model or vendor:
            monitors.append(
                {
                    "model": model or "Monitor",
                    "vendor": vendor,
                    "driver": block_driver(block),
                }
            )

    if monitors:
        return monitors

    return [
        {
            "model": value,
            "vendor": None,
            "driver": None,
        }
        for value in short.get("monitor", [])
    ]


# ============================================================
# USB
# ============================================================

def parse_usb(blocks, short):
    usb_blocks = get_blocks(
        blocks,
        classes=["usb"],
        keywords=[
            "usb",
            "unifying receiver",
            "webcam",
        ],
    )

    usb = []

    for block in usb_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
        )

        vendor = block_vendor(block)

        if model or vendor:
            usb.append(
                {
                    "model": model or "USB device",
                    "vendor": vendor,
                    "driver": block_driver(block),
                }
            )

    return usb


# ============================================================
# AUDIO
# ============================================================

def parse_audio(blocks, short):
    audio_blocks = get_blocks(
        blocks,
        classes=["sound"],
        keywords=[
            "sound",
            "audio",
            "multimedia",
        ],
    )

    audio = []

    for block in audio_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
        )

        vendor = block_vendor(block)

        if model or vendor:
            audio.append(
                {
                    "model": model or "Audio device",
                    "vendor": vendor,
                    "driver": block_driver(block),
                }
            )

    if audio:
        return audio

    return [
        {
            "model": value,
            "vendor": None,
            "driver": None,
        }
        for value in short.get("sound", [])
    ]


# ============================================================
# BLUETOOTH
# ============================================================

def parse_bluetooth(blocks, short):
    bluetooth_blocks = get_blocks(
        blocks,
        classes=["bluetooth"],
        keywords=[
            "bluetooth",
        ],
    )

    result = []

    for block in bluetooth_blocks:
        props = block["properties"]

        result.append(
            {
                "model": first_value(
                    props,
                    "model",
                    "device",
                ) or "Bluetooth",
                "vendor": block_vendor(block),
                "driver": block_driver(block),
            }
        )

    if result:
        return result

    return [
        {
            "model": value,
            "vendor": None,
            "driver": None,
        }
        for value in short.get("bluetooth", [])
    ]


# ============================================================
# CAMERA
# ============================================================

def parse_cameras(blocks, short):
    camera_blocks = get_blocks(
        blocks,
        classes=["camera"],
        keywords=[
            "camera",
            "webcam",
            "uvc",
        ],
    )

    result = []

    for block in camera_blocks:
        props = block["properties"]

        result.append(
            {
                "model": first_value(
                    props,
                    "model",
                    "device",
                ) or "Camera",
                "vendor": block_vendor(block),
                "driver": block_driver(block),
            }
        )

    return result


# ============================================================
# SYSTEM / BIOS
# ============================================================

def parse_system(blocks):
    bios_blocks = get_blocks(
        blocks,
        classes=["bios"],
        keywords=["bios"],
    )

    bios = {}

    if bios_blocks:
        props = bios_blocks[0]["properties"]

        bios = {
            "vendor": first_value(
                props,
                "vendor",
                "manufacturer",
            ),
            "model": first_value(
                props,
                "model",
            ),
            "version": first_value(
                props,
                "version",
                "revision",
            ),
        }

    return bios


# ============================================================
# BUILD DATA
# ============================================================

def build_data(detailed, short_text):
    blocks = parse_hwinfo_blocks(detailed)
    short = parse_hwinfo_short(short_text)

    data = {
        "cpu": parse_cpu(blocks, short),
        "memory": get_system_memory(),
        "gpu": parse_gpu(blocks, short),
        "disks": parse_disks(blocks, short),
        "network": parse_network(blocks, short),
        "monitors": parse_monitors(blocks, short),
        "usb": parse_usb(blocks, short),
        "audio": parse_audio(blocks, short),
        "bluetooth": parse_bluetooth(blocks, short),
        "cameras": parse_cameras(blocks, short),
        "system": parse_system(blocks),
        "raw_short": short,
        "raw_blocks": blocks,
    }

    return data


# ============================================================
# HTML
# ============================================================

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>Hardware Dashboard</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        Inter,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    background: #0b0d11;
    color: #e8eaed;
}

.app {
    display: flex;
    min-height: 100vh;
}

/* ============================================================
   SIDEBAR
   ============================================================ */

.sidebar {
    width: 235px;
    background: #11141a;
    border-right: 1px solid #242832;

    padding: 22px 14px;

    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
}

.logo {
    font-size: 19px;
    font-weight: 700;
    padding: 0 10px 25px;
}

.logo span {
    color: #8ab4f8;
}

.nav {
    display: flex;
    flex-direction: column;
    gap: 5px;
}

.nav button {
    border: 0;
    background: transparent;
    color: #9aa0a6;

    text-align: left;

    padding: 11px 12px;
    border-radius: 8px;

    cursor: pointer;

    font-size: 14px;
}

.nav button:hover,
.nav button.active {
    background: #1d2532;
    color: white;
}

/* ============================================================
   CONTENT
   ============================================================ */

.content {
    margin-left: 235px;
    width: calc(100% - 235px);

    padding: 30px;

    max-width: 1500px;
}

.page {
    display: none;
}

.page.active {
    display: block;
}

h1 {
    margin-top: 0;
    margin-bottom: 6px;

    font-size: 28px;
}

.subtitle {
    color: #8c929b;
    margin-bottom: 28px;
}

/* ============================================================
   CARDS
   ============================================================ */

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));

    gap: 15px;
}

.card {
    background: #12161d;
    border: 1px solid #252a33;

    border-radius: 12px;

    padding: 18px;

    min-height: 100px;
}

.card-title {
    color: #8c929b;
    font-size: 12px;
    text-transform: uppercase;

    letter-spacing: .06em;

    margin-bottom: 10px;
}

.card-value {
    font-size: 19px;
    font-weight: 650;

    word-break: break-word;
}

.card-small {
    color: #8c929b;
    font-size: 13px;

    margin-top: 7px;
}

/* ============================================================
   SECTIONS
   ============================================================ */

.section {
    background: #12161d;

    border: 1px solid #252a33;

    border-radius: 12px;

    padding: 20px;

    margin-bottom: 18px;
}

.section h2 {
    margin-top: 0;

    font-size: 17px;
}

/* ============================================================
   DEVICES
   ============================================================ */

.device {
    border-top: 1px solid #242832;

    padding: 15px 0;
}

.device:first-child {
    border-top: 0;
    padding-top: 0;
}

.device-name {
    font-weight: 650;
    margin-bottom: 6px;
}

.device-meta {
    color: #9097a1;
    font-size: 13px;

    display: flex;
    flex-wrap: wrap;

    gap: 14px;
}

/* ============================================================
   BADGES
   ============================================================ */

.badge {
    display: inline-block;

    background: #1d2532;
    color: #8ab4f8;

    font-size: 11px;
    font-weight: 650;

    padding: 3px 8px;
    border-radius: 6px;

    margin-left: 8px;

    vertical-align: middle;
}

.badge-up {
    background: #113322;
    color: #7ee787;
}

.badge-down {
    background: #3a1a1a;
    color: #f85149;
}

/* ============================================================
   CHART
   ============================================================ */

.chart-container {
    position: relative;

    height: 280px;

    margin-top: 15px;
}

/* ============================================================
   TABLE
   ============================================================ */

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    text-align: left;

    padding: 10px;

    border-bottom: 1px solid #252a33;

    font-size: 13px;
}

th {
    color: #9097a1;
}

/* ============================================================
   RAW
   ============================================================ */

details {
    background: #0e1116;

    border: 1px solid #252a33;

    border-radius: 8px;

    margin-bottom: 8px;
}

summary {
    padding: 12px;

    cursor: pointer;

    color: #c9ced6;
}

pre {
    padding: 15px;

    overflow: auto;

    font-size: 11px;

    color: #9aa0a6;

    white-space: pre-wrap;
}

/* ============================================================
   MOBILE
   ============================================================ */

@media (max-width: 800px) {

    .sidebar {
        width: 70px;
    }

    .logo {
        font-size: 0;
    }

    .logo span {
        font-size: 20px;
    }

    .nav button {
        font-size: 0;
        text-align: center;
    }

    .content {
        margin-left: 70px;
        width: calc(100% - 70px);

        padding: 20px;
    }
}

</style>
</head>

<body>

<div class="app">

    <aside class="sidebar">

        <div class="logo">
            Hardware <span>Dashboard</span>
        </div>

        <div class="nav">

            <button class="active"
                    onclick="showPage('overview', this)">
                Overview
            </button>

            <button onclick="showPage('cpu', this)">
                CPU
            </button>

            <button onclick="showPage('gpu', this)">
                GPU
            </button>

            <button onclick="showPage('memory', this)">
                Memory
            </button>

            <button onclick="showPage('storage', this)">
                Storage
            </button>

            <button onclick="showPage('network', this)">
                Network
            </button>

            <button onclick="showPage('devices', this)">
                Devices
            </button>

            <button onclick="showPage('raw', this)">
                Raw hwinfo
            </button>

        </div>

    </aside>


    <main class="content">

        <!-- ==================================================
             OVERVIEW
        =================================================== -->

        <section id="overview" class="page active">

            <h1>Hardware Overview</h1>

            <div class="subtitle">
                Información detectada automáticamente mediante hwinfo y lsblk.
            </div>

            <div id="overviewCards"
                 class="grid">
            </div>

            <div class="section">

                <h2>Storage</h2>

                <div class="chart-container">
                    <canvas id="storageChart"></canvas>
                </div>

            </div>

        </section>


        <!-- ==================================================
             CPU
        =================================================== -->

        <section id="cpu" class="page">

            <h1>CPU</h1>

            <div class="subtitle">
                Procesador y CPUs lógicas detectadas.
            </div>

            <div id="cpuContent"></div>

        </section>


        <!-- ==================================================
             GPU
        =================================================== -->

        <section id="gpu" class="page">

            <h1>GPU</h1>

            <div class="subtitle">
                Adaptadores gráficos detectados.
            </div>

            <div id="gpuContent"></div>

        </section>


        <!-- ==================================================
             MEMORY
        =================================================== -->

        <section id="memory" class="page">

            <h1>Memory</h1>

            <div class="subtitle">
                Memoria RAM instalada.
            </div>

            <div id="memoryContent"></div>

        </section>


        <!-- ==================================================
             STORAGE
        =================================================== -->

        <section id="storage" class="page">

            <h1>Storage</h1>

            <div class="subtitle">
                Discos físicos (vía lsblk) con sus particiones, tamaño exacto,
                tipo (HDD/SSD/NVMe) y punto de montaje.
            </div>

            <div id="storageContent"></div>

        </section>


        <!-- ==================================================
             NETWORK
        =================================================== -->

        <section id="network" class="page">

            <h1>Network</h1>

            <div class="subtitle">
                Interfaces y adaptadores de red.
            </div>

            <div id="networkContent"></div>

        </section>


        <!-- ==================================================
             DEVICES
        =================================================== -->

        <section id="devices" class="page">

            <h1>Devices</h1>

            <div class="subtitle">
                Periféricos y otros dispositivos detectados.
            </div>

            <div id="devicesContent"></div>

        </section>


        <!-- ==================================================
             RAW
        =================================================== -->

        <section id="raw" class="page">

            <h1>Raw hwinfo</h1>

            <div class="subtitle">
                Datos técnicos originales utilizados por el dashboard.
            </div>

            <div id="rawContent"></div>

        </section>

    </main>

</div>


<script>

const DATA = __HWINFO_DATA__;


// ============================================================
// HELPERS
// ============================================================

function escapeHtml(value) {

    if (value === null ||
        value === undefined) {
        return "";
    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function displayValue(value, fallback = "—") {

    if (value === null ||
        value === undefined ||
        value === "") {
        return fallback;
    }

    return escapeHtml(value);
}


function deviceHtml(device) {

    const stateBadge = device.state
        ? `<span class="badge ${device.state === "UP" ? "badge-up" : "badge-down"}">${escapeHtml(device.state)}</span>`
        : "";

    const ipBadges = (device.ip_addresses && device.ip_addresses.length)
        ? `
            <div class="device-meta" style="margin-top:6px;">
                ${device.ip_addresses.map(ip => `
                    <span class="badge">
                        ${escapeHtml(ip.address)}${ip.prefix ? "/" + escapeHtml(ip.prefix) : ""}
                    </span>
                `).join("")}
            </div>
        `
        : "";

    return `
        <div class="device">

            <div class="device-name">
                ${displayValue(device.model, "Dispositivo")}
                ${stateBadge}
            </div>

            <div class="device-meta">

                ${device.vendor
                    ? `<span>Vendor: ${escapeHtml(device.vendor)}</span>`
                    : ""}

                ${device.driver
                    ? `<span>Driver: ${escapeHtml(device.driver)}</span>`
                    : ""}

                ${device.interface
                    ? `<span>Interface: ${escapeHtml(device.interface)}</span>`
                    : ""}

                ${device.mac
                    ? `<span>MAC: ${escapeHtml(device.mac)}</span>`
                    : ""}

                ${device.mtu
                    ? `<span>MTU: ${escapeHtml(device.mtu)}</span>`
                    : ""}

                ${device.bus_id
                    ? `<span>Bus: ${escapeHtml(device.bus_id)}</span>`
                    : ""}

                ${device.device
                    ? `<span>Device: ${escapeHtml(device.device)}</span>`
                    : ""}

                ${device.size
                    ? `<span>Size: ${escapeHtml(device.size)}</span>`
                    : ""}

            </div>

            ${ipBadges}

        </div>
    `;
}


function renderDevices(containerId, devices) {

    const container =
        document.getElementById(containerId);

    if (!devices || devices.length === 0) {

        container.innerHTML = `
            <div class="card-small">
                No se detectaron dispositivos.
            </div>
        `;

        return;
    }

    container.innerHTML =
        devices.map(deviceHtml).join("");
}


// ============================================================
// NAVIGATION
// ============================================================

function showPage(pageId, button) {

    document
        .querySelectorAll(".page")
        .forEach(page => {
            page.classList.remove("active");
        });

    document
        .querySelectorAll(".nav button")
        .forEach(btn => {
            btn.classList.remove("active");
        });

    document
        .getElementById(pageId)
        .classList.add("active");

    button.classList.add("active");
}


// ============================================================
// OVERVIEW
// ============================================================

function renderOverview() {

    const cpu = DATA.cpu || {};
    const memory = DATA.memory || {};
    const gpu = DATA.gpu || [];
    const disks = DATA.disks || [];
    const network = DATA.network || [];

    const cards = [

        {
            title: "CPU",
            value: cpu.model || "No detectado",
            small:
                cpu.physical_cores && cpu.logical_processors
                    ? `${cpu.physical_cores} núcleos · ${cpu.logical_processors} hilos`
                    : cpu.logical_processors
                        ? `${cpu.logical_processors} CPUs lógicas`
                        : ""
        },

        {
            title: "Memory",
            value:
                memory.total_gb
                    ? `${memory.total_gb} GB`
                    : "No detectada",
            small:
                memory.modules && memory.modules.length
                    ? `${memory.modules.length} módulo(s) físico(s)`
                    : "RAM total"
        },

        {
            title: "GPU",
            value:
                gpu.length
                    ? gpu[0].model
                    : "No detectada",
            small:
                gpu.length > 1
                    ? `${gpu.length} GPUs detectadas`
                    : ""
        },

        {
            title: "Storage",
            value:
                disks.length
                    ? `${disks.length} disco(s)`
                    : "No detectado",
            small:
                disks.map(d => d.size_human)
                    .filter(Boolean)
                    .join(" · ")
        },

        {
            title: "Network",
            value:
                network.length
                    ? `${network.length} interfaces`
                    : "No detectada",
            small:
                network.filter(n => n.state === "UP").length
                    ? `${network.filter(n => n.state === "UP").length} activa(s)`
                    : network
                        .map(n => n.interface)
                        .filter(Boolean)
                        .join(" · ")
        },

        {
            title: "Monitor",
            value:
                DATA.monitors?.length
                    ? DATA.monitors[0].model
                    : "No detectado",
            small:
                DATA.monitors?.length > 1
                    ? `${DATA.monitors.length} monitores`
                    : ""
        },

    ];


    document.getElementById("overviewCards").innerHTML =
        cards.map(card => `
            <div class="card">

                <div class="card-title">
                    ${escapeHtml(card.title)}
                </div>

                <div class="card-value">
                    ${escapeHtml(card.value)}
                </div>

                <div class="card-small">
                    ${escapeHtml(card.small || "")}
                </div>

            </div>
        `).join("");
}


// ============================================================
// CPU
// ============================================================

function renderCPU() {

    const cpu = DATA.cpu || {};
    const cache = cpu.cache || {};

    const freqLabel = (mhz) =>
        mhz ? (mhz / 1000).toFixed(2) + " GHz" : "—";

    document.getElementById("cpuContent").innerHTML = `

        <div class="grid">

            <div class="card">
                <div class="card-title">Model</div>
                <div class="card-value">${displayValue(cpu.model)}</div>
                <div class="card-small">${displayValue(cpu.architecture, "")}</div>
            </div>

            <div class="card">
                <div class="card-title">Vendor</div>
                <div class="card-value">${displayValue(cpu.vendor)}</div>
            </div>

            <div class="card">
                <div class="card-title">Topología</div>
                <div class="card-value">
                    ${cpu.physical_cores ? cpu.physical_cores + " núcleos" : "—"}
                    ${cpu.logical_processors ? " / " + cpu.logical_processors + " hilos" : ""}
                </div>
                <div class="card-small">
                    ${cpu.sockets ? cpu.sockets + " socket(s)" : ""}
                    ${cpu.threads_per_core ? ` · ${cpu.threads_per_core} hilos/núcleo` : ""}
                </div>
            </div>

            <div class="card">
                <div class="card-title">Frecuencia</div>
                <div class="card-value">
                    ${cpu.max_mhz ? freqLabel(cpu.max_mhz) + " máx" : "—"}
                </div>
                <div class="card-small">
                    ${cpu.min_mhz ? "mín " + freqLabel(cpu.min_mhz) : ""}
                </div>
            </div>

            <div class="card">
                <div class="card-title">Cache</div>
                <div class="card-value" style="font-size: 15px;">
                    L1d ${displayValue(cache.l1d)} · L1i ${displayValue(cache.l1i)}
                </div>
                <div class="card-small">
                    L2 ${displayValue(cache.l2)} · L3 ${displayValue(cache.l3)}
                </div>
            </div>

            <div class="card">
                <div class="card-title">Virtualización</div>
                <div class="card-value">${displayValue(cpu.virtualization)}</div>
            </div>

        </div>


        <div class="section">

            <h2>Frecuencia actual por núcleo lógico</h2>

            <div class="chart-container">

                <canvas id="cpuChart"></canvas>

            </div>

        </div>
    `;


    const frequencies =
        cpu.frequencies || [];

    // Con lscpu/proc_cpuinfo las frecuencias ya llegan como números
    // (MHz reales, leídos en el momento). Solo en el último fallback
    // de hwinfo pueden llegar como texto tipo "2400MHz".
    const values = frequencies
        .map(value => {

            if (typeof value === "number") {
                return value;
            }

            const match =
                String(value)
                    .match(/([\d.]+)\s*MHz/i);

            return match
                ? parseFloat(match[1])
                : null;

        })
        .filter(value => value !== null);


    if (!values.length) {
        return;
    }


    new Chart(
        document.getElementById("cpuChart"),
        {
            type: "bar",

            data: {

                labels:
                    values.map(
                        (_, index) =>
                            `CPU ${index + 1}`
                    ),

                datasets: [
                    {
                        label: "MHz",
                        data: values,
                    }
                ]

            },

            options: {

                responsive: true,

                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: false
                    }
                }

            }
        }
    );
}


// ============================================================
// GPU
// ============================================================

function renderGPU() {

    renderDevices(
        "gpuContent",
        DATA.gpu || []
    );
}


// ============================================================
// MEMORY
// ============================================================

function renderMemory() {

    const memory =
        DATA.memory || {};

    const modules =
        memory.modules || [];

    const modulesHtml = modules.length
        ? `
            <div class="section">

                <h2>Módulos instalados</h2>

                <table>

                    <thead>
                        <tr>
                            <th>Slot</th>
                            <th>Tamaño</th>
                            <th>Tipo</th>
                            <th>Velocidad</th>
                            <th>Fabricante</th>
                            <th>Part number</th>
                        </tr>
                    </thead>

                    <tbody>

                        ${modules.map(m => `
                            <tr>
                                <td>${displayValue(m.locator)}</td>
                                <td>${displayValue(m.size)}</td>
                                <td>${displayValue(m.type)}</td>
                                <td>${displayValue(m.configured_speed || m.speed)}</td>
                                <td>${displayValue(m.manufacturer)}</td>
                                <td>${displayValue(m.part_number)}</td>
                            </tr>
                        `).join("")}

                    </tbody>

                </table>

            </div>
        `
        : `
            <div class="card-small">
                No se pudo leer el detalle por módulo (requiere
                dmidecode con permisos de root). Se muestra solo el
                total del sistema.
            </div>
        `;

    document.getElementById(
        "memoryContent"
    ).innerHTML = `

        <div class="grid">

            <div class="card">

                <div class="card-title">
                    Total RAM
                </div>

                <div class="card-value">
                    ${
                        memory.total_gb
                            ? memory.total_gb + " GB"
                            : "—"
                    }
                </div>

                <div class="card-small">
                    ${
                        modules.length
                            ? modules.length + " módulo(s) físico(s)"
                            : ""
                    }
                </div>

            </div>

        </div>

        ${modulesHtml}

    `;
}


// ============================================================
// STORAGE
// ============================================================
//
// Cada disco viene de lsblk con su tamaño exacto en bytes (no de
// hwinfo), su tipo real (HDD/SSD/NVMe/Desconocido) y la lista de
// particiones con su propio tamaño/filesystem/mountpoint.

function partitionsTableHtml(partitions) {

    if (!partitions || !partitions.length) {
        return `
            <div class="card-small">
                No se detectaron particiones (o el disco no tiene
                tabla de particiones).
            </div>
        `;
    }

    return `
        <table>

            <thead>
                <tr>
                    <th>Partición</th>
                    <th>Tamaño</th>
                    <th>Filesystem</th>
                    <th>Mountpoint</th>
                </tr>
            </thead>

            <tbody>

                ${partitions.map(p => `
                    <tr>
                        <td>${displayValue(p.device)}</td>
                        <td>${displayValue(p.size_human)}</td>
                        <td>${displayValue(p.filesystem)}</td>
                        <td>${displayValue(p.mountpoint)}</td>
                    </tr>
                `).join("")}

            </tbody>

        </table>
    `;
}


function diskCardHtml(disk) {

    return `
        <div class="section">

            <h2>
                ${displayValue(disk.device)} — ${displayValue(disk.model)}
                ${disk.type
                    ? `<span class="badge">${escapeHtml(disk.type)}</span>`
                    : ""}
                ${disk.removable
                    ? `<span class="badge">Extraíble</span>`
                    : ""}
            </h2>

            <div class="device-meta" style="margin-bottom:14px;">

                ${disk.vendor
                    ? `<span>Vendor: ${escapeHtml(disk.vendor)}</span>`
                    : ""}

                ${disk.serial
                    ? `<span>Serial: ${escapeHtml(disk.serial)}</span>`
                    : ""}

                ${disk.transport
                    ? `<span>Interfaz: ${escapeHtml(disk.transport.toUpperCase())}</span>`
                    : ""}

                ${disk.size_human
                    ? `<span>Tamaño: ${escapeHtml(disk.size_human)}</span>`
                    : `<span>Tamaño: no disponible</span>`}

                ${disk.partition_table
                    ? `<span>Tabla: ${escapeHtml(disk.partition_table.toUpperCase())}</span>`
                    : ""}

                ${(!disk.partitions || !disk.partitions.length) && disk.filesystem
                    ? `<span>Filesystem: ${escapeHtml(disk.filesystem)}</span>`
                    : ""}

                ${(!disk.partitions || !disk.partitions.length) && disk.mountpoint
                    ? `<span>Mountpoint: ${escapeHtml(disk.mountpoint)}</span>`
                    : ""}

            </div>

            ${partitionsTableHtml(disk.partitions)}

        </div>
    `;
}


function renderStorage() {

    const disks =
        DATA.disks || [];

    const container =
        document.getElementById("storageContent");

    if (!disks.length) {

        container.innerHTML = `
            <div class="card">
                No se detectaron discos.
            </div>
        `;

        return;
    }

    container.innerHTML =
        disks.map(diskCardHtml).join("");
}


// ============================================================
// NETWORK
// ============================================================

function renderNetwork() {

    renderDevices(
        "networkContent",
        DATA.network || []
    );
}


// ============================================================
// DEVICES
// ============================================================

function renderDevicesPage() {

    const container =
        document.getElementById(
            "devicesContent"
        );

    const sections = [

        ["USB", DATA.usb || []],

        ["Audio", DATA.audio || []],

        ["Bluetooth", DATA.bluetooth || []],

        ["Cameras", DATA.cameras || []],

        ["Monitors", DATA.monitors || []],

    ];


    container.innerHTML =
        sections.map(
            ([title, devices]) => `

                <div class="section">

                    <h2>
                        ${escapeHtml(title)}
                    </h2>

                    ${
                        devices.length
                            ? devices.map(deviceHtml).join("")
                            : `<div class="card-small">
                                No detectado.
                               </div>`
                    }

                </div>

            `
        ).join("");
}


// ============================================================
// STORAGE CHART
// ============================================================
//
// Usa directamente disk.size_gb (calculado en Python a partir de
// bytes exactos de lsblk). Ya no se parsean strings como "500G".

function renderStorageChart() {

    const disks =
        DATA.disks || [];

    if (!disks.length) {
        return;
    }

    const labels =
        disks.map(
            disk =>
                disk.model ||
                disk.device ||
                "Disco"
        );

    const sizes =
        disks.map(
            disk => disk.size_gb || 0
        );

    new Chart(
        document.getElementById(
            "storageChart"
        ),
        {
            type: "bar",

            data: {

                labels,

                datasets: [
                    {
                        label: "GB",
                        data: sizes
                    }
                ]

            },

            options: {

                responsive: true,

                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: false
                    }
                }

            }
        }
    );
}


// ============================================================
// RAW
// ============================================================

function renderRaw() {

    const blocks =
        DATA.raw_blocks || [];

    document.getElementById(
        "rawContent"
    ).innerHTML =
        blocks.map(
            block => {

                const properties =
                    block.properties || {};

                return `

                    <details>

                        <summary>
                            ${escapeHtml(
                                block.id +
                                ": " +
                                block.header
                            )}
                        </summary>

                        <pre>${escapeHtml(
                            JSON.stringify(
                                properties,
                                null,
                                2
                            )
                        )}</pre>

                    </details>

                `;

            }
        ).join("");
}


// ============================================================
// INIT
// ============================================================

renderOverview();
renderCPU();
renderGPU();
renderMemory();
renderStorage();
renderNetwork();
renderDevicesPage();
renderStorageChart();
renderRaw();

</script>

</body>
</html>
"""


# ============================================================
# HTML GENERATION
# ============================================================

def generate_html(data):
    serialized = json.dumps(
        data,
        ensure_ascii=False,
    )

    html = HTML_TEMPLATE.replace(
        "__HWINFO_DATA__",
        serialized,
    )

    output = (
        Path(tempfile.gettempdir())
        / "hwinfo_dashboard.html"
    )

    output.write_text(
        html,
        encoding="utf-8",
    )

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    try:

        detailed, short = get_hwinfo()

        print("Parseando información...")

        data = build_data(
            detailed,
            short,
        )

        output = generate_html(data)

        print()
        print("Dashboard generado:")
        print(output)
        print()

        webbrowser.open(
            output.as_uri()
        )

    except KeyboardInterrupt:

        print("\nCancelado.")

    except Exception as exc:

        print(
            f"\nERROR: {exc}"
        )

        raise


if __name__ == "__main__":
    main()
