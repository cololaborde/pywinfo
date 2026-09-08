import re

def clean_value(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Quitar comillas exteriores
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]

    value = value.strip()

    return value or None


def parse_value(value):
    """
    Convierte:

        "Intel Corporation"
        1234
        cfg=new, avail=yes

    en valores limpios.
    """

    value = clean_value(value)

    if value is None:
        return None

    # No intentamos convertir agresivamente números porque
    # hwinfo utiliza muchos identificadores hexadecimales.
    return value


def normalize_key(key):
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def normalize_bool(value):
    """
    Convierte valores típicos de lsblk (bool nativo, "0"/"1",
    "yes"/"no") a True/False/None.
    """

    if isinstance(value, bool):
        return value

    if value is None:
        return None

    value = str(value).strip().lower()

    if value in ("1", "yes", "true"):
        return True

    if value in ("0", "no", "false"):
        return False

    return None


def safe_int(value):
    try:
        if value is None:
            return None

        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value):
    try:
        if value is None:
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def format_bytes(size_bytes):
    """
    Convierte un tamaño en bytes a una representación legible,
    p.ej. 500107862016 -> "465.8 GB".
    """

    if not size_bytes:
        return None

    size = float(size_bytes)

    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(size)} {unit}"

            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{size:.1f} PB"


def first_value(data, *keys):
    """
    Busca la primera clave disponible.
    """

    for key in keys:
        normalized = normalize_key(key)

        if normalized in data:
            value = data[normalized]

            if isinstance(value, list):
                if value:
                    return value[0]
            elif value:
                return value

    return None


def all_values(data, *keys):
    result = []

    for key in keys:
        normalized = normalize_key(key)

        value = data.get(normalized)

        if value is None:
            continue

        if isinstance(value, list):
            result.extend(value)
        else:
            result.append(value)

    return result