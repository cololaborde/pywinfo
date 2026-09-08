import shutil
import subprocess

def command_exists(command):
    return shutil.which(command) is not None


def install_hwinfo():
    if command_exists("hwinfo"):
        return

    print("hwinfo no está instalado. Intentando instalarlo...")

    commands = []

    if command_exists("dnf"):
        commands = [
            ["sudo", "dnf", "install", "-y", "hwinfo"],
        ]
    elif command_exists("apt"):
        commands = [
            ["sudo", "apt", "update"],
            ["sudo", "apt", "install", "-y", "hwinfo"],
        ]
    elif command_exists("pacman"):
        commands = [
            ["sudo", "pacman", "-Sy", "--noconfirm", "hwinfo"],
        ]
    elif command_exists("zypper"):
        commands = [
            ["sudo", "zypper", "--non-interactive", "install", "hwinfo"],
        ]

    if not commands:
        raise RuntimeError(
            "No encontré un gestor de paquetes compatible "
            "(dnf, apt, pacman o zypper)."
        )

    for command in commands:
        subprocess.run(command, check=True)

    if not command_exists("hwinfo"):
        raise RuntimeError("No se pudo instalar hwinfo.")


def run_command(command, sudo=False):
    if sudo:
        command = ["sudo"] + command

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Error ejecutando {' '.join(command)}:\n{result.stderr}"
        )

    return result.stdout


def get_hwinfo():
    install_hwinfo()

    # Sin root, hwinfo omite bastante información (BIOS/DMI, algunos
    # recursos de bus, etc). Lo corremos con sudo para tener el detalle
    # completo.
    print("Obteniendo información detallada de hardware (sudo)...")
    detailed = run_command(["hwinfo"], sudo=True)

    print("Obteniendo resumen...")
    short = run_command(["hwinfo", "--short"], sudo=True)

    return detailed, short