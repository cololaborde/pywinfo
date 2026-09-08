#!/usr/bin/env python3

import webbrowser

from src.data import build_data
from src.system import get_hwinfo
from src.report.generator import generate_html


def main():

    try:

        detailed, short = get_hwinfo()

        print("Parseando información...")

        data = build_data(
            detailed,
            short,
        )

        output = generate_html(data)

        print()
        print("Dashboard generado:")
        print(output)
        print()

        webbrowser.open(
            output.as_uri()
        )

    except KeyboardInterrupt:

        print("\nCancelado.")

    except Exception as exc:

        print(
            f"\nERROR: {exc}"
        )

        raise


if __name__ == "__main__":
    main()