from src.utils import first_value
from src.hwinfo_parser import get_blocks


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