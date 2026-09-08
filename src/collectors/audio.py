from src.utils import first_value
from src.hwinfo_parser import get_blocks, block_vendor, block_driver


def parse_audio(blocks, short):
    audio_blocks = get_blocks(
        blocks,
        classes=["sound"],
        keywords=[
            "sound",
            "audio",
            "multimedia",
        ],
    )

    audio = []

    for block in audio_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
        )

        vendor = block_vendor(block)

        if model or vendor:
            audio.append(
                {
                    "model": model or "Audio device",
                    "vendor": vendor,
                    "driver": block_driver(block),
                }
            )

    if audio:
        return audio

    return [
        {
            "model": value,
            "vendor": None,
            "driver": None,
        }
        for value in short.get("sound", [])
    ]