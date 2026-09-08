import json

from ..system import command_exists, run_command
from ..utils import safe_int, normalize_bool, clean_value, format_bytes
from ..hwinfo_parser import get_blocks, block_vendor, first_value

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