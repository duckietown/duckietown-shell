import hashlib
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import uuid
from xml.parsers.expat import ExpatError

from .exceptions import UserError


def get_device_id() -> str:
    try:
        if sys.platform.startswith("linux"):
            try:
                value = Path("/etc/machine-id").read_text().strip()
            except FileNotFoundError:
                value = Path("/var/lib/dbus/machine-id").read_text().strip()
            machine_id = uuid.UUID(value).hex
        elif sys.platform == "darwin":
            output = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice", "-a"],
                stderr=subprocess.PIPE,
                timeout=5,
            )
            devices = plistlib.loads(output)
            if not isinstance(devices, list) or not devices or not isinstance(devices[0], dict):
                raise UserError("macOS did not return a computer identity.")
            value = devices[0].get("IOPlatformUUID")
            if not isinstance(value, str):
                raise UserError("macOS did not return a computer UUID.")
            machine_id = uuid.UUID(value).hex
        elif sys.platform == "win32":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
            if not isinstance(value, str):
                raise UserError("Windows did not return a computer GUID.")
            machine_id = uuid.UUID(value).hex
        else:
            raise UserError(f"Computer registration for 'ente' is not supported on '{sys.platform}'.")
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        plistlib.InvalidFileException,
        ExpatError,
    ) as error:
        raise UserError(f"Could not identify this computer for 'ente': {error}") from error
    if machine_id == "0" * 32:
        raise UserError("This computer has an uninitialized machine identity.")
    return hashlib.sha256(f"duckietown-ente-device-v1:{machine_id}".encode("ascii")).hexdigest()


def get_device_parameters() -> dict:
    try:
        hostname = socket.gethostname()
    except OSError as error:
        raise UserError(f"Could not read this computer's hostname: {error}") from error
    return {"device_id": get_device_id(), "device_hostname": hostname}
