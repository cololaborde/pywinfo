from ..utils import first_value
from ..hwinfo_parser import get_blocks, block_vendor, block_driver


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