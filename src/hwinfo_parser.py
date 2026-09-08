import re
import json
from src.utils import normalize_key, parse_value, first_value

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