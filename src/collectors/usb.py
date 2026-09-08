from src.utils import first_value
from src.hwinfo_parser import get_blocks, block_vendor, block_driver


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