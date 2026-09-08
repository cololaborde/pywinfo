from ..utils import first_value
from ..hwinfo_parser import get_blocks, block_driver


def parse_gpu(blocks, short):
    gpu_blocks = get_blocks(
        blocks,
        classes=["graphics", "display"],
        keywords=[
            "graphics",
            "vga",
            "display controller",
        ],
    )

    gpus = []

    for block in gpu_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
        )

        vendor = first_value(
            props,
            "vendor",
        )

        driver = block_driver(block)

        bus_id = first_value(
            props,
            "sysfs_busid",
            "sysfs_id",
        )

        if model or vendor:
            gpus.append(
                {
                    "model": model or "GPU",
                    "vendor": vendor,
                    "driver": driver,
                    "bus_id": bus_id,
                }
            )

    if gpus:
        return gpus

    short_gpus = short.get("graphics_card", [])

    return [
        {
            "model": value,
            "vendor": None,
            "driver": None,
            "bus_id": None,
        }
        for value in short_gpus
    ]