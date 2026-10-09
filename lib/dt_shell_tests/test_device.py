import hashlib
import plistlib
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from dt_shell.device import get_device_id, get_device_parameters
from dt_shell.exceptions import UserError


MACHINE_ID = "12345678123456781234567812345678"
MACHINE_UUID = "12345678-1234-5678-1234-567812345678"
DEVICE_ID = hashlib.sha256(f"duckietown-ente-device-v1:{MACHINE_ID}".encode("ascii")).hexdigest()


class DeviceIdentityTests(unittest.TestCase):
    def test_linux_identity_is_stable_normalized_and_hashed(self):
        with patch("dt_shell.device.sys.platform", "linux"), patch(
            "dt_shell.device.Path.read_text",
            return_value=MACHINE_ID.upper() + "\n",
        ):
            self.assertEqual(DEVICE_ID, get_device_id())

    def test_linux_dbus_identity_is_used_if_etc_identity_is_absent(self):
        with patch("dt_shell.device.sys.platform", "linux"), patch(
            "dt_shell.device.Path.read_text",
            side_effect=[FileNotFoundError(), MACHINE_ID],
        ):
            self.assertEqual(DEVICE_ID, get_device_id())

    def test_invalid_uninitialized_and_unreadable_linux_identities_fail_explicitly(self):
        for value in ("", "not-a-machine-id", "0" * 32):
            with self.subTest(value=value), patch("dt_shell.device.sys.platform", "linux"), patch(
                "dt_shell.device.Path.read_text",
                return_value=value,
            ):
                with self.assertRaises(UserError):
                    get_device_id()
        with patch("dt_shell.device.sys.platform", "linux"), patch(
            "dt_shell.device.Path.read_text",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaisesRegex(UserError, "Could not identify"):
                get_device_id()

    def test_macos_uses_platform_uuid_without_unbounded_subprocesses(self):
        with patch("dt_shell.device.sys.platform", "darwin"), patch(
            "dt_shell.device.subprocess.check_output",
            return_value=plistlib.dumps([{"IOPlatformUUID": MACHINE_UUID}]),
        ) as command:
            self.assertEqual(DEVICE_ID, get_device_id())
        self.assertEqual(5, command.call_args.kwargs["timeout"])

    def test_missing_macos_identity_is_reported(self):
        for value in ([], [{}], "invalid"):
            with self.subTest(value=value), patch("dt_shell.device.sys.platform", "darwin"), patch(
                "dt_shell.device.subprocess.check_output",
                return_value=plistlib.dumps(value),
            ):
                with self.assertRaises(UserError):
                    get_device_id()

    def test_malformed_macos_identity_output_is_reported(self):
        with patch("dt_shell.device.sys.platform", "darwin"), patch(
            "dt_shell.device.subprocess.check_output",
            return_value=b'<?xml version="1.0"?><plist><array',
        ):
            with self.assertRaisesRegex(UserError, "Could not identify"):
                get_device_id()

    def test_windows_uses_machine_guid_from_the_machine_registry(self):
        registry = SimpleNamespace(
            HKEY_LOCAL_MACHINE=0,
            KEY_READ=1,
            KEY_WOW64_64KEY=2,
            OpenKey=MagicMock(),
            QueryValueEx=MagicMock(return_value=(MACHINE_UUID, 1)),
        )
        with patch("dt_shell.device.sys.platform", "win32"), patch.dict("sys.modules", {"winreg": registry}):
            self.assertEqual(DEVICE_ID, get_device_id())

    def test_unsupported_platform_is_reported(self):
        with patch("dt_shell.device.sys.platform", "unsupported"):
            with self.assertRaisesRegex(UserError, "not supported"):
                get_device_id()

    def test_parameters_include_hostname_but_not_raw_machine_id(self):
        with patch("dt_shell.device.get_device_id", return_value=DEVICE_ID), patch(
            "dt_shell.device.socket.gethostname",
            return_value="computer-a",
        ):
            self.assertEqual(
                {"device_id": DEVICE_ID, "device_hostname": "computer-a"},
                get_device_parameters(),
            )
