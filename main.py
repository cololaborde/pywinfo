#!/usr/bin/env python3

import json
import os
import re
import tempfile
import webbrowser
from pathlib import Path
from template import HTML_TEMPLATE
from system import get_hwinfo, command_exists, run_command
from hwinfo_parser import parse_hwinfo_blocks, parse_hwinfo_short, get_blocks, \
                            block_driver, block_vendor
from utils import normalize_key, first_value, safe_int, safe_float, normalize_bool, \
                            clean_value, format_bytes

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
