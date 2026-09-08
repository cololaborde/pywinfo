from src.utils import first_value
from src.hwinfo_parser import get_blocks, block_vendor, block_driver


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