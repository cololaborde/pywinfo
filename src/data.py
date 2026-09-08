from .hwinfo_parser import parse_hwinfo_blocks, parse_hwinfo_short
from .collectors import (
    cpu,
    memory,
    gpu,
    disks,
    network,
    monitors,
    usb,
    audio,
    bluetooth,
    cameras,
    bios,
)


def build_data(detailed, short_text):
    blocks = parse_hwinfo_blocks(detailed)
    short = parse_hwinfo_short(short_text)

    data = {
        "cpu": cpu.parse_cpu(blocks, short),
        "memory": memory.get_system_memory(),
        "gpu": gpu.parse_gpu(blocks, short),
        "disks": disks.parse_disks(blocks, short),
        "network": network.parse_network(blocks, short),
        "monitors": monitors.parse_monitors(blocks, short),
        "usb": usb.parse_usb(blocks, short),
        "audio": audio.parse_audio(blocks, short),
        "bluetooth": bluetooth.parse_bluetooth(blocks, short),
        "cameras": cameras.parse_cameras(blocks, short),
        "system": bios.parse_system(blocks),
        "raw_short": short,
        "raw_blocks": blocks,
    }

    return data