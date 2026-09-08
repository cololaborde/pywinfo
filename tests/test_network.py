from unittest import mock

from src.hwinfo_parser import (
    parse_hwinfo_blocks,
    parse_hwinfo_short,
)
from src.collectors import network


def test_build_hw_network_map(hwinfo_sample):
    blocks = parse_hwinfo_blocks(hwinfo_sample)

    hw_map, unmatched = network.build_hw_network_map(blocks)

    assert hw_map["enp3s0"]["model"] == "Realtek Ethernet Connection (4) I219-V"
    assert hw_map["enp3s0"]["vendor"] == 'pci 0x8086 "Intel Corporation"'
    assert hw_map["enp3s0"]["driver"] == "e1000e"

    assert hw_map["wlo1"]["model"] == "Intel Wireless 8265 / 8275"
    assert hw_map["wlo1"]["driver"] == "iwlwifi"

    assert unmatched == []


def test_parse_network(hwinfo_sample):
    blocks = parse_hwinfo_blocks(hwinfo_sample)

    ip_data = [
        {
            "ifname": "enp3s0",
            "operstate": "UP",
            "address": "aa:bb:cc:dd:ee:ff",
            "mtu": 1500,
            "addr_info": [
                {
                    "local": "192.168.1.10",
                    "prefixlen": 24,
                    "family": "inet",
                }
            ],
        }
    ]

    with mock.patch(
        "src.collectors.network.get_ip_addr_json",
        return_value=ip_data,
    ):
        result = network.parse_network(blocks, {})

    by_name = {entry["interface"]: entry for entry in result}

    assert "enp3s0" in by_name
    assert by_name["enp3s0"]["model"] == "Realtek Ethernet Connection (4) I219-V"
    assert by_name["enp3s0"]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert by_name["enp3s0"]["state"] == "UP"
    assert by_name["enp3s0"]["ip_addresses"][0]["address"] == "192.168.1.10"

    # Detectada por hwinfo pero no reportada por `ip`.
    assert by_name["wlo1"]["model"] == "Intel Wireless 8265 / 8275"
    assert by_name["wlo1"]["mac"] is None
    assert by_name["wlo1"]["state"] is None
    assert by_name["wlo1"]["ip_addresses"] == []


def test_parse_network_skips_loopback(hwinfo_sample):
    blocks = parse_hwinfo_blocks(hwinfo_sample)

    ip_data = [
        {
            "ifname": "lo",
            "operstate": "UNKNOWN",
            "address": "00:00:00:00:00:00",
            "addr_info": [
                {
                    "local": "127.0.0.1",
                    "prefixlen": 8,
                    "family": "inet",
                }
            ],
        }
    ]

    with mock.patch(
        "src.collectors.network.get_ip_addr_json",
        return_value=ip_data,
    ):
        result = network.parse_network(blocks, {})

    assert all(entry["interface"] != "lo" for entry in result)