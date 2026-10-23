import socket

import dt_shell_device

from .exceptions import UserError


def get_device_id() -> str:
    try:
        return dt_shell_device.get_device_id()
    except dt_shell_device.DeviceIdentityError as error:
        raise UserError(str(error)) from error


def get_device_parameters() -> dict:
    try:
        hostname = socket.gethostname()
    except OSError as error:
        raise UserError(f"Could not read this computer's hostname: {error}") from error
    return {"device_id": get_device_id(), "device_hostname": hostname}
