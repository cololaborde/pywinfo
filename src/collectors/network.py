import re
import json

from src.system import command_exists, run_command
from src.utils import clean_value, first_value
from src.hwinfo_parser import get_blocks, block_vendor, block_driver


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