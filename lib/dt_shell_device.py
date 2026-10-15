"""Computer identity shared by the trusted bootstrap and DTS plan authorization."""

import hashlib
from pathlib import Path
import plistlib
import re
import socket
import subprocess
import sys
import uuid
from xml.parsers.expat import ExpatError


class DeviceIdentityError(RuntimeError):
    pass


def _fingerprint(value: str) -> str:
    machine_id = uuid.UUID(value).hex
    if machine_id == "0" * 32:
        raise DeviceIdentityError("This computer has an uninitialized machine identity.")
    return hashlib.sha256(
        f"duckietown-ente-device-v1:{machine_id}".encode("ascii")
    ).hexdigest()


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
            if (
                not isinstance(devices, list)
                or not devices
                or not isinstance(devices[0], dict)
            ):
                raise DeviceIdentityError("macOS did not return a computer identity.")
            value = devices[0].get("IOPlatformUUID")
            if not isinstance(value, str):
                raise DeviceIdentityError("macOS did not return a computer UUID.")
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
                raise DeviceIdentityError("Windows did not return a computer GUID.")
            machine_id = uuid.UUID(value).hex
        else:
            raise DeviceIdentityError(
                f"Computer identification is not supported on '{sys.platform}'."
            )
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        plistlib.InvalidFileException,
        ExpatError,
    ) as error:
        raise DeviceIdentityError(
            f"Could not identify this computer: {error}"
        ) from error
    # Preserve the fingerprint used by existing computer registrations.
    return _fingerprint(machine_id)


def get_renderer_device_id(os_family: str) -> str:
    own_family = {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform)
    if os_family == own_family or os_family == "webgl":
        return get_device_id()
    if sys.platform == "linux" and os_family == "windows":
        try:
            if "microsoft" not in Path("/proc/sys/kernel/osrelease").read_text().lower():
                raise DeviceIdentityError("Windows renderer interoperation requires WSL.")
            output = subprocess.check_output(
                [
                    "reg.exe", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography",
                    "/v", "MachineGuid", "/reg:64",
                ],
                stderr=subprocess.PIPE,
                timeout=5,
            ).decode("utf-8", errors="strict")
            match = re.search(r"MachineGuid\s+REG_SZ\s+([0-9a-fA-F-]+)", output)
            if match is None:
                raise DeviceIdentityError("Windows did not return a computer GUID through WSL.")
            return _fingerprint(match.group(1))
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as error:
            raise DeviceIdentityError(f"Could not identify the Windows renderer computer: {error}") from error
    raise DeviceIdentityError(
        f"Cannot launch a '{os_family}' renderer from this '{own_family}' DTS host."
    )


def get_device_parameters() -> dict:
    try:
        hostname = socket.gethostname()
    except OSError as error:
        raise DeviceIdentityError(
            f"Could not read this computer's hostname: {error}"
        ) from error
    return {"device_id": get_device_id(), "device_hostname": hostname}
