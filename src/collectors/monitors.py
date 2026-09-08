from src.utils import first_value
from src.hwinfo_parser import get_blocks, block_vendor, block_driver


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