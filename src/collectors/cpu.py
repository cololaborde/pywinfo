import json
import re

from src.system import command_exists, run_command
from src.utils import safe_int, safe_float, first_value
from src.hwinfo_parser import get_blocks


def get_lscpu():
    """
    lscpu -J es la fuente correcta para topología de CPU: sockets,
    cores físicos vs hilos, cache por nivel, MHz min/max reales.
    hwinfo reporta un bloque por CPU lógica y su "Clock" no siempre
    refleja el turbo/min real, así que lo dejamos solo como último
    fallback más abajo.
    """

    if not command_exists("lscpu"):
        return None

    try:
        output = run_command(["lscpu", "-J"])
        data = json.loads(output)
    except Exception:
        return None

    result = {}

    def walk(items):
        for item in items or []:
            field = (item.get("field") or "").rstrip(":").strip()

            if field:
                result[field] = item.get("data")

            walk(item.get("children"))

    walk(data.get("lscpu", []))

    return result or None


def get_proc_cpuinfo_frequencies():
    """
    Frecuencias actuales por núcleo lógico, en tiempo real, leídas
    directamente del kernel en vez de un valor estático de hwinfo.
    """

    frequencies = []

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("cpu mhz"):
                    match = re.search(r"([\d.]+)", line)

                    if match:
                        frequencies.append(float(match.group(1)))
    except Exception:
        pass

    return frequencies


def get_proc_cpuinfo_summary():
    """
    Fallback cuando no hay lscpu: reconstruye modelo, sockets y
    cores físicos a partir de /proc/cpuinfo (physical id / core id).
    """

    try:
        with open("/proc/cpuinfo") as f:
            content = f.read()
    except Exception:
        return None

    model = None
    vendor = None
    logical = 0
    physical_ids = set()
    core_ids = set()

    for entry in content.split("\n\n"):
        fields = {}

        for line in entry.splitlines():
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()

        if "processor" not in fields:
            continue

        logical += 1

        if model is None:
            model = fields.get("model name")

        if vendor is None:
            vendor = fields.get("vendor_id")

        if "physical id" in fields and "core id" in fields:
            physical_ids.add(fields["physical id"])
            core_ids.add((fields["physical id"], fields["core id"]))

    if logical == 0:
        return None

    return {
        "model": model,
        "vendor": vendor,
        "architecture": None,
        "sockets": len(physical_ids) or None,
        "physical_cores": len(core_ids) or None,
        "threads_per_core": None,
        "logical_processors": logical,
        "max_mhz": None,
        "min_mhz": None,
        "cache": {},
        "virtualization": None,
        "frequencies": [],
    }


def empty_result(model=None, vendor=None, logical=0, freqs=None):
    return {
        "model": model,
        "vendor": vendor,
        "architecture": None,
        "sockets": None,
        "physical_cores": None,
        "threads_per_core": None,
        "logical_processors": logical,
        "max_mhz": None,
        "min_mhz": None,
        "cache": {},
        "virtualization": None,
        "frequencies": freqs or [],
    }


def parse_cpu(blocks, short):
    frequencies = get_proc_cpuinfo_frequencies()

    # --- Fuente primaria: lscpu -J ---
    lscpu = get_lscpu()

    if lscpu:
        sockets = safe_int(lscpu.get("Socket(s)"))
        cores_per_socket = safe_int(lscpu.get("Core(s) per socket"))
        threads_per_core = safe_int(lscpu.get("Thread(s) per core"))
        logical = safe_int(lscpu.get("CPU(s)"))

        physical_cores = (
            sockets * cores_per_socket
            if sockets and cores_per_socket
            else None
        )

        return {
            "model": lscpu.get("Model name") or lscpu.get("Model"),
            "vendor": lscpu.get("Vendor ID"),
            "architecture": lscpu.get("Architecture"),
            "sockets": sockets,
            "physical_cores": physical_cores,
            "threads_per_core": threads_per_core,
            "logical_processors": logical or (len(frequencies) or None),
            "max_mhz": safe_float(lscpu.get("CPU max MHz")),
            "min_mhz": safe_float(lscpu.get("CPU min MHz")),
            "cache": {
                "l1d": lscpu.get("L1d cache"),
                "l1i": lscpu.get("L1i cache"),
                "l2": lscpu.get("L2 cache"),
                "l3": lscpu.get("L3 cache"),
            },
            "virtualization": lscpu.get("Virtualization"),
            "frequencies": frequencies,
        }

    # --- Fallback: /proc/cpuinfo ---
    proc_summary = get_proc_cpuinfo_summary()

    if proc_summary:
        proc_summary["frequencies"] = (
            frequencies or proc_summary["frequencies"]
        )
        return proc_summary

    # --- Último fallback: hwinfo (menos confiable para clocks/cache) ---
    cpu_blocks = get_blocks(
        blocks,
        classes=["cpu", "processor"],
        keywords=[
            "processor",
            "cpu",
            "core",
            "intel(r)",
            "amd",
        ],
    )

    cpus = []

    for block in cpu_blocks:
        props = block["properties"]

        model = first_value(
            props,
            "model",
            "device",
            "processor",
        )

        vendor = first_value(
            props,
            "vendor",
        )

        clock = first_value(
            props,
            "clock",
            "current_clock",
            "frequency",
        )

        if not model:
            continue

        cpus.append(
            {
                "model": model,
                "vendor": vendor,
                "clock": clock,
            }
        )

    if cpus:
        model_counts = {}

        for cpu in cpus:
            key = cpu["model"]
            model_counts[key] = model_counts.get(key, 0) + 1

        main_model = max(model_counts, key=model_counts.get)

        hwinfo_freqs = [cpu["clock"] for cpu in cpus if cpu["clock"]]

        return empty_result(
            model=main_model,
            vendor=cpus[0].get("vendor"),
            logical=len(cpus),
            freqs=hwinfo_freqs,
        )

    # Fallback al short
    short_cpus = short.get("cpu", [])

    if short_cpus:
        models = []

        for value in short_cpus:
            model = re.sub(
                r",\s*[\d.]+\s*MHz.*$",
                "",
                value,
                flags=re.IGNORECASE,
            ).strip()

            if model:
                models.append(model)

        if models:
            counts = {}

            for model in models:
                counts[model] = counts.get(model, 0) + 1

            return empty_result(
                model=max(counts, key=counts.get),
                logical=len(models),
                freqs=short_cpus,
            )

    return empty_result()