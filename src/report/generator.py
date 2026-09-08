import json
import tempfile
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = REPORT_DIR / "assets"


def generate_html(data, output_path=None):
    """
    Lee template.html + assets y genera el HTML final autónomo
    (una sola hoja), inyectando el JSON con los datos en
    `__HWINFO_DATA__`.
    """
    template = (REPORT_DIR / "template.html").read_text(
        encoding="utf-8"
    )
    style_css = (ASSETS_DIR / "style.css").read_text(
        encoding="utf-8"
    )
    app_js = (ASSETS_DIR / "app.js").read_text(
        encoding="utf-8"
    )

    serialized = json.dumps(
        data,
        ensure_ascii=False,
    )

    html = (
        template.replace("__STYLE_CSS__", style_css)
        .replace("__APP_JS__", app_js)
        .replace("__HWINFO_DATA__", serialized)
    )

    if output_path is None:
        output_path = (
            Path(tempfile.gettempdir())
            / "hwinfo_dashboard.html"
        )

    output_path = Path(output_path)

    output_path.write_text(
        html,
        encoding="utf-8",
    )

    return output_path