import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dt_authentication import DuckietownToken
from dt_authentication.token import CURVE
from ecdsa import SigningKey
import yaml


KEYS = os.environ.get("DTS_DEVELOPER_TEST_KEYS")
ROOT = os.environ.get("DTS_DEVELOPER_TEST_ROOT")


@unittest.skipUnless(
    KEYS and ROOT,
    "Run tools/developer_test.py with an isolated, re-keyed native bootstrap",
)
class NativeDeveloperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = {
            issuer: serialization.load_pem_private_key(
                Path(path).read_bytes(), password=None
            )
            for issuer, path in json.loads(Path(KEYS).read_text()).items()
        }
        cls.installation = Path(ROOT)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dts-developer-profile-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.identity_key = SigningKey.generate(curve=CURVE)
        self.uid = 42
        self.identity = DuckietownToken.generate(
            self.identity_key,
            self.uid,
            days=1,
            hours=0,
            minutes=0,
            scope=["auth"],
            version="dt2",
        ).as_string()
        self.issuer = "https://hub.duckietown.com"
        self.profile = self.home / "profiles" / "daffy"
        self.env = dict(os.environ)
        for name in (
            "DTSHELL_LIB",
            "DTSHELL_COMMANDS",
            "DTSHELL_PYTHONPATH",
            "DTSHELL_PROFILE",
            "DTSHELL_DISTRO",
            "DTSHELL_TOKEN",
            "DUCKIETOWN_TOKEN",
            "DTHUB_HOST",
            "DTHUB_URL",
            "IGNORE_ENVIRONMENTS",
        ):
            self.env.pop(name, None)
        self.env.update(
            {
                "PYTHONPATH": str(self.installation),
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "DTSHELL_ROOT": str(self.home / "shell"),
                "DTSHELL_DATABASES": str(self.home / "databases"),
                "DTSHELL_PROFILES": str(self.home / "profiles"),
                "DTHUB_URL": self.issuer,
                "PYTHONUTF8": "1",
            }
        )
        self.write_database(
            self.home / "databases/settings.yaml",
            {
                "profile": "daffy",
                "check_for_updates": False,
                "show_billboards": False,
            },
        )
        self.write_database(
            self.home / "databases/profiles.yaml", {"daffy": str(self.profile)}
        )
        self.write_database(
            self.profile / "databases/settings.yaml", {"distro": "daffy"}
        )
        self.write_database(
            self.profile / "databases/secrets.yaml", {"token/dt1": self.identity}
        )
        self.write_database(
            self.profile / "databases/updates_check.yaml",
            {"upload_events": time.time()},
        )
        self.write_database(
            self.home / "databases/updates_check.yaml", {"billboards": time.time()}
        )
        self.library = self.home / "library"
        package = self.library / "dt_shell"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(
            "print('AUTHORIZED_LIBRARY_LOADED')\nraise SystemExit(0)\n",
            encoding="ascii",
        )
        result = self.run_python(
            "import dt_shell_device; print(dt_shell_device.get_device_id())"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.device = result.stdout.strip()

    def write_database(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({"version": 1, "data": data}), encoding="utf-8")

    def grant(self, *, issuer=None, key=None, **changes):
        now = int(time.time())
        claims = {
            "format": 1,
            "audience": "duckietown-shell-developer",
            "capability": "develop:dts",
            "issuer": issuer or self.issuer,
            "uid": self.uid,
            "identity_sha256": hashlib.sha256(self.identity.encode()).hexdigest(),
            "device_id": self.device,
            "is_staff": True,
            "is_superuser": False,
            "issued_at": now,
            "expires_at": now + 3600,
            "renewable": False,
        }
        claims.update(changes)
        content = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode(
            "ascii"
        )
        signature = (key or self.keys[issuer or self.issuer]).sign(content)
        return json.dumps(
            {
                "payload": base64.b64encode(content).decode("ascii"),
                "signature": base64.b64encode(signature).decode("ascii"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def cache_path(self, *, issuer=None, identity=None):
        digest = hashlib.sha256((identity or self.identity).encode()).hexdigest()
        key = hashlib.sha256(
            f"{issuer or self.issuer}:{digest}:{self.device}".encode("ascii")
        ).hexdigest()
        return self.profile / "databases/developer" / (key + ".json")

    def cache(self, grant=None, **context):
        path = self.cache_path(**context)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(grant or self.grant(), encoding="ascii")
        return path

    def prefix(self):
        return (
            "from dt_authentication.token import PUBLIC_KEYS; "
            f"PUBLIC_KEYS['dt2'] = {self.identity_key.verifying_key.to_pem().decode()!r}; "
            "import dt_shell_release; from unittest.mock import patch, Mock; import sys\n"
        )

    def run_python(self, body, *, overrides=None, extra=None, arguments=()):
        env = dict(self.env)
        env.update(overrides or {})
        env.update(extra or {})
        return subprocess.run(
            [sys.executable, "-c", self.prefix() + body, *arguments],
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def launch(self, **extra):
        return self.run_python(
            "dt_shell_release.launch()",
            overrides={"DTSHELL_LIB": str(self.library)},
            **extra,
        )

    def assert_blocked(self, result, reason=None):
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        if reason:
            self.assertIn(reason, result.stdout + result.stderr)
        self.assertNotIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)
        self.assertNotIn(self.identity, result.stdout + result.stderr)

    def response(self, token=None, *, success=True):
        return (
            f"response = Mock(is_redirect=False, content=b'fixture'); response.json.return_value = "
            f"{ {'success': success, 'result': {'token': token or self.grant()}, 'messages': []}!r}\n"
        )

    def source_commands(self, *, extra_import=False, virtual=False):
        path = self.home / "commands"
        config = path / "__command_set__"
        config.mkdir(parents=True)
        (config / "configuration.py").write_text(
            "from dt_shell.commands import DTCommandSetConfigurationAbs\n"
            "from dt_shell.environments import VirtualPython3Environment\n"
            "VERSION = '0.0.0'\n"
            "class DTCommandSetConfiguration(DTCommandSetConfigurationAbs):\n"
            " @classmethod\n def version(cls): return 0, 0, 0\n"
            " @classmethod\n def minimum_shell_version(cls): return 0, 0, 0\n"
            " @classmethod\n def maximum_shell_version(cls): return 999, 999, 999\n"
            + (
                " @classmethod\n def default_environment(cls): return VirtualPython3Environment()\n"
                if virtual
                else ""
            ),
            encoding="ascii",
        )
        (config / "init.py").write_text("INITIALIZED = True\n", encoding="ascii")
        utility = path / "utils"
        utility.mkdir()
        (utility / "__init__.py").write_text("", encoding="ascii")
        (utility / "table_utils.py").write_text(
            "def format_matrix(*args, **kwargs): return ''\n", encoding="ascii"
        )
        command = path / "probe"
        command.mkdir()
        (command / "__init__.py").write_text("", encoding="ascii")
        (command / "command.py").write_text(
            "from dt_shell import DTCommandAbs\n"
            + ("import developer_extra\n" if extra_import else "")
            + "class DTCommand(DTCommandAbs):\n"
            " @staticmethod\n def command(shell, args): print('AUTHORIZED_COMMAND_EXECUTED')\n",
            encoding="ascii",
        )
        subprocess.run(
            ["git", "init", "-q", str(path)], check=True, capture_output=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "remote",
                "add",
                "origin",
                "https://github.com/duckietown/duckietown-shell-commands",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "-c",
                "user.name=DTS Developer Tests",
                "-c",
                "user.email=developer-tests@example.invalid",
                "commit",
                "-qm",
                "Safe local command fixture\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>",
            ],
            check=True,
            capture_output=True,
        )
        return path

    def test_normal_release_startup_does_not_require_a_developer_grant_or_hub_request(
        self,
    ):
        result = self.run_python(
            "with patch('requests.post', side_effect=AssertionError('Unexpected developer request')):\n"
            " dt_shell_release.verify_installation(); assert not dt_shell_release.is_developer_mode()\n"
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_staff_superuser_and_combined_grants_enable_library_override(self):
        for staff, superuser in ((True, False), (False, True), (True, True)):
            with self.subTest(staff=staff, superuser=superuser):
                self.cache(self.grant(is_staff=staff, is_superuser=superuser))
                result = self.launch()
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)
                self.assertIn("Authenticated developer mode", result.stderr)
                self.assertIn("UTC", result.stderr)
                self.assertNotIn(self.identity, result.stdout + result.stderr)

    def test_valid_cached_grant_works_offline_without_refresh(self):
        self.cache()
        result = self.run_python(
            "with patch('requests.post', side_effect=AssertionError('Offline grant must not refresh')):\n"
            " dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)

    def test_first_startup_obtains_valid_bound_grant_before_import_and_caches_privately(
        self,
    ):
        result = self.run_python(
            self.response()
            + "with patch('requests.post', return_value=response) as request:\n"
            " dt_shell_release.verify_installation()\n"
            " values = request.call_args.kwargs\n"
            f" assert values['json']['device_id'] == {self.device!r}\n"
            " assert values['allow_redirects'] is False\n"
            f" assert values['headers']['Authorization'] == 'Token ' + {self.identity!r}\n"
            " dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)
        path = self.cache_path()
        self.assertTrue(path.exists())
        if os.name != "nt":
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_expired_cache_is_refreshed_before_source_import(self):
        now = int(time.time())
        self.cache(self.grant(issued_at=now - 3700, expires_at=now - 100))
        result = self.run_python(
            self.response()
            + "with patch('requests.post', return_value=response):\n dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(
            base64.b64decode(json.loads(self.cache_path().read_text())["payload"])
        )
        self.assertGreater(payload["expires_at"], time.time())

    def test_denied_or_unsigned_staff_responses_never_load_source(self):
        for response in (
            {
                "success": False,
                "messages": ["Staff or superuser privileges required"],
                "result": {},
                "code": 403,
            },
            {"success": True, "result": {"is_staff": True, "is_superuser": True}},
            {"success": True, "result": {"token": '{"is_staff":true}'}},
        ):
            with self.subTest(response=response):
                result = self.run_python(
                    f"response = Mock(is_redirect=False, content=b'fixture'); response.json.return_value = {response!r}\n"
                    "with patch('requests.post', return_value=response):\n dt_shell_release.launch()\n",
                    overrides={"DTSHELL_LIB": str(self.library)},
                )
                self.assert_blocked(result, "Developer authorization failed")
                self.assertFalse(self.cache_path().exists())

    def test_removed_privileges_block_refresh_after_offline_grant_expiry(self):
        now = int(time.time())
        self.cache(self.grant(issued_at=now - 3700, expires_at=now - 100))
        result = self.run_python(
            "response = Mock(is_redirect=False, content=b'fixture'); response.json.return_value = "
            "{'success': False, 'messages': ['Privileges removed'], 'result': {}, 'code': 403}\n"
            "with patch('requests.post', return_value=response):\n dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
        )
        self.assert_blocked(result, "Privileges removed")

    def test_expired_grant_cannot_fall_back_when_hub_is_offline(self):
        now = int(time.time())
        self.cache(self.grant(issued_at=now - 3700, expires_at=now - 100))
        result = self.run_python(
            "import requests\nwith patch('requests.post', side_effect=requests.ConnectionError('offline')):\n"
            " dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
        )
        self.assert_blocked(result, "unexpired signed grant is required offline")

    def test_tampered_wrong_key_wrong_user_device_scope_and_lifetime_grants_are_rejected(
        self,
    ):
        now = int(time.time())
        for token in (
            self.grant(key=Ed25519PrivateKey.generate()),
            self.grant(uid=self.uid + 1),
            self.grant(device_id="0" * 64),
            self.grant(identity_sha256="1" * 64),
            self.grant(capability="use:ente"),
            self.grant(audience="duckietown-ente"),
            self.grant(is_staff=False, is_superuser=False),
            self.grant(is_staff="true"),
            self.grant(uid=True),
            self.grant(format=True),
            self.grant(renewable=True),
            self.grant(expires_at=now + 86400),
            self.grant(issued_at=now + 120, expires_at=now + 3720),
            "{}",
        ):
            with self.subTest(token_length=len(token)):
                self.cache(token)
                result = self.run_python(
                    "with patch('requests.post', side_effect=AssertionError('Invalid cache must not refresh')):\n"
                    " dt_shell_release.launch()\n",
                    overrides={"DTSHELL_LIB": str(self.library)},
                )
                self.assert_blocked(result, "Developer authorization failed")

    def test_changing_identity_cannot_reuse_another_users_grant(self):
        token = self.grant()
        identity = DuckietownToken.generate(
            self.identity_key,
            43,
            days=1,
            hours=0,
            minutes=0,
            scope=["auth"],
            version="dt2",
        ).as_string()
        self.write_database(
            self.profile / "databases/secrets.yaml", {"token/dt1": identity}
        )
        self.cache(token, identity=identity)
        self.assert_blocked(self.launch(), "does not authorize this user")

    def test_production_and_staging_keys_are_pinned_to_their_own_issuers(self):
        staging = "https://staging-hub.duckietown.com"
        self.cache(self.grant(issuer=staging), issuer=staging)
        result = self.launch(extra={"DTHUB_URL": staging})
        self.assertEqual(0, result.returncode, result.stderr)
        self.cache(
            self.grant(issuer=staging, key=self.keys[self.issuer]), issuer=staging
        )
        self.assert_blocked(
            self.launch(extra={"DTHUB_URL": staging}), "signature is invalid"
        )
        self.cache(self.grant(issuer=staging))
        self.assert_blocked(self.launch(), "signature is invalid")

    def test_arbitrary_hub_and_runtime_key_overrides_are_not_trusted(self):
        result = self.run_python(
            "with patch('requests.post', side_effect=AssertionError('Unapproved URL was contacted')):\n"
            " dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
            extra={
                "DTHUB_URL": "https://untrusted.invalid",
                "DTS_DEVELOPER_PUBLIC_KEYS": "{}",
            },
        )
        self.assert_blocked(result, "not an approved")
        self.cache(self.grant(key=Ed25519PrivateKey.generate()))
        self.assert_blocked(
            self.launch(extra={"DTS_DEVELOPER_PUBLIC_KEYS": "{}"}),
            "signature is invalid",
        )

    def test_identity_token_must_be_dt2_auth_not_a_plan_or_developer_grant(self):
        identity = DuckietownToken.generate(
            self.identity_key,
            self.uid,
            days=1,
            hours=0,
            minutes=0,
            scope=["use:ente"],
            version="dt2",
        ).as_string()
        self.write_database(
            self.profile / "databases/secrets.yaml", {"token/dt1": identity}
        )
        self.assert_blocked(self.launch(), "cannot identify your account")
        self.write_database(
            self.profile / "databases/secrets.yaml", {"token/dt1": self.grant()}
        )
        self.assert_blocked(self.launch(), "requires a DT2")

    def test_redirected_requests_do_not_forward_credentials_or_import_source(self):
        result = self.run_python(
            "response = Mock(is_redirect=True)\n"
            "with patch('requests.post', return_value=response):\n dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
        )
        self.assert_blocked(result, "credentials were not forwarded")

    def test_exported_verifiers_cannot_bypass_private_bootstrap_authorization(self):
        self.cache(self.grant(key=Ed25519PrivateKey.generate()))
        result = self.run_python(
            "dt_shell_release.verify_installation = lambda: None\n"
            "dt_shell_release.verify_developer_authorization = lambda: None\n"
            "dt_shell_release.is_developer_mode = lambda: True\n"
            "dt_shell_release.launch()\n",
            overrides={"DTSHELL_LIB": str(self.library)},
        )
        self.assert_blocked(result, "signature is invalid")

    def test_management_status_renew_and_clear_ignore_all_source_overrides(self):
        invalid = {
            "DTSHELL_LIB": str(self.library),
            "DTSHELL_COMMANDS": "",
            "DTSHELL_PYTHONPATH": "",
        }
        status = self.run_python(
            "dt_shell_release.launch()",
            overrides=invalid,
            arguments=("developer", "status"),
        )
        self.assertEqual(0, status.returncode, status.stderr)
        self.assertIn("No cached developer grant", status.stdout)
        self.assertNotIn("AUTHORIZED_LIBRARY_LOADED", status.stdout)
        renewed = self.run_python(
            self.response()
            + "with patch('requests.post', return_value=response):\n dt_shell_release.launch()\n",
            overrides=invalid,
            arguments=("developer", "renew"),
        )
        self.assertEqual(0, renewed.returncode, renewed.stderr)
        self.assertIn("Developer grant: valid", renewed.stdout)
        self.assertNotIn("AUTHORIZED_LIBRARY_LOADED", renewed.stdout)
        self.assertNotIn(self.identity, renewed.stdout + renewed.stderr)
        cleared = self.run_python(
            "dt_shell_release.launch()",
            overrides=invalid,
            arguments=("developer", "clear"),
        )
        self.assertEqual(0, cleared.returncode, cleared.stderr)
        self.assertFalse(self.cache_path().exists())

    def test_status_is_local_and_reports_readable_expired_grant_without_renewal(self):
        now = int(time.time())
        self.cache(self.grant(issued_at=now - 3700, expires_at=now - 100))
        result = self.run_python(
            "with patch('requests.post', side_effect=AssertionError('Status must be offline')):\n"
            " dt_shell_release.launch()\n",
            arguments=("developer", "status"),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Developer grant: expired at", result.stdout)
        self.assertIn("UTC", result.stdout)

    def test_developer_help_is_available_without_a_token_or_loading_overrides(self):
        self.write_database(self.profile / "databases/secrets.yaml", {})
        for arguments in (("developer",), ("developer", "--help"), ("developer", "-h")):
            with self.subTest(arguments=arguments):
                result = self.run_python(
                    "dt_shell_release.launch()",
                    overrides={"DTSHELL_LIB": str(self.library)},
                    arguments=arguments,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("subcommands:", result.stdout)
                for subcommand in ("status", "renew", "clear"):
                    self.assertIn(subcommand, result.stdout)
                self.assertNotIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)

    def test_developer_leaf_help_precedes_identity_and_invalid_source_overrides(self):
        self.write_database(self.profile / "databases/secrets.yaml", {})
        for subcommand in ("status", "renew", "clear"):
            for help_flag in ("--help", "-h"):
                with self.subTest(subcommand=subcommand, flag=help_flag):
                    result = self.run_python(
                        "with patch('requests.post', side_effect=AssertionError('Help must be offline')):\n"
                        " dt_shell_release.launch()\n",
                        overrides={
                            "DTSHELL_LIB": str(self.library),
                            "DTSHELL_COMMANDS": "",
                            "DTSHELL_PYTHONPATH": "",
                        },
                        arguments=("--profile", "daffy", "developer", subcommand, help_flag),
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn(f"developer {subcommand}", result.stdout)
                    self.assertNotIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)

    def test_invalid_developer_subcommands_and_arguments_do_not_require_identity(self):
        self.write_database(self.profile / "databases/secrets.yaml", {})
        for arguments in (
            ("developer", "unknown"),
            ("developer", "status", "renew"),
            ("developer", "renew", "unexpected"),
            ("developer", "clear", "--unknown"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_python(
                    "with patch('requests.post', side_effect=AssertionError('Invalid syntax must be offline')):\n"
                    " dt_shell_release.launch()\n",
                    overrides={"DTSHELL_LIB": str(self.library)},
                    arguments=arguments,
                )
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertIn("usage:", result.stderr)
                self.assertNotIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)

    def test_selected_profile_and_environment_identity_fallback_match_native_authentication(
        self,
    ):
        self.write_database(
            self.home / "databases/settings.yaml", {"profile": "unconfigured"}
        )
        self.write_database(self.profile / "databases/secrets.yaml", {})
        self.cache()
        for argument in (("--profile", "daffy"), ("--profile=daffy",)):
            with self.subTest(argument=argument):
                result = self.run_python(
                    "dt_shell_release.launch()",
                    overrides={"DTSHELL_LIB": str(self.library)},
                    extra={"DTSHELL_TOKEN": self.identity},
                    arguments=argument,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("AUTHORIZED_LIBRARY_LOADED", result.stdout)

    def test_developer_mode_still_rejects_modified_installed_payloads(self):
        self.cache()
        path = self.installation / "dt_shell/assets/requirements.txt"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"\n# modified payload\n")
            self.assert_blocked(self.launch(), "has been modified")
        finally:
            path.write_bytes(original)

    def test_noncanonical_duplicate_malformed_or_oversized_grants_do_not_refresh(self):
        envelope = json.loads(self.grant())
        content = base64.b64decode(envelope["payload"])
        claims = json.loads(content)
        variants = [
            json.dumps(
                {"payload": envelope["payload"], "signature": "!invalid-base64!"}
            ),
            json.dumps(
                {
                    "payload": envelope["payload"],
                    "signature": base64.b64encode(b"bad").decode("ascii"),
                }
            ),
            '{"payload":"bad",' + self.grant()[1:],
            "x" * 17000,
        ]
        for payload in (
            content + b"\n",
            json.dumps(claims, indent=2).encode("ascii"),
            b'{"uid":42,"uid":43}',
        ):
            variants.append(
                json.dumps(
                    {
                        "payload": base64.b64encode(payload).decode("ascii"),
                        "signature": base64.b64encode(
                            self.keys[self.issuer].sign(payload)
                        ).decode("ascii"),
                    }
                )
            )
        for token in variants:
            with self.subTest(token_length=len(token)):
                self.cache(token)
                result = self.run_python(
                    "with patch('requests.post', side_effect=AssertionError('Malformed cache must not refresh')):\n"
                    " dt_shell_release.launch()\n",
                    overrides={"DTSHELL_LIB": str(self.library)},
                )
                self.assert_blocked(result, "Developer authorization failed")

    def test_monotonic_deadline_cannot_be_extended_by_rolling_back_the_wall_clock(self):
        self.cache()
        extra = self.home / "extra"
        extra.mkdir()
        result = self.run_python(
            "dt_shell_release.verify_installation()\n"
            f"with patch('time.time', return_value={time.time()!r}), "
            f"patch('time.monotonic', return_value={time.monotonic() + 7200!r}):\n"
            " dt_shell_release.verify_installation()\n",
            overrides={"DTSHELL_PYTHONPATH": str(extra)},
        )
        self.assert_blocked(result, "Developer authorization expired")

    def test_pythonpath_uses_platform_separator_and_checks_every_approved_directory(
        self,
    ):
        self.cache()
        first, second = self.home / "first", self.home / "second"
        first.mkdir()
        second.mkdir()
        (first / "first_developer_helper.py").write_text(
            "VALUE = 1\n", encoding="ascii"
        )
        (second / "second_developer_helper.py").write_text(
            "VALUE = 2\n", encoding="ascii"
        )
        result = self.run_python(
            "dt_shell_release.verify_installation(); import os\n"
            "sys.path.extend(os.environ['DTSHELL_PYTHONPATH'].split(os.pathsep))\n"
            "import first_developer_helper, second_developer_helper\n"
            "assert first_developer_helper.VALUE + second_developer_helper.VALUE == 3\n",
            overrides={
                "DTSHELL_PYTHONPATH": os.pathsep.join((str(first), str(second)))
            },
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_expired_active_session_cannot_import_new_source_or_run_dispatch(self):
        self.cache()
        extra = self.home / "extra"
        extra.mkdir()
        (extra / "developer_late.py").write_text(
            "print('UNAUTHORIZED_LATE_IMPORT')\n", encoding="ascii"
        )
        result = self.run_python(
            "dt_shell_release.verify_installation()\n"
            f"sys.path.insert(0, {str(extra)!r})\n"
            f"with patch('time.time', return_value={time.time() + 7200!r}):\n import developer_late\n",
            overrides={"DTSHELL_PYTHONPATH": str(extra)},
        )
        self.assert_blocked(result, "Developer authorization expired")
        self.assertNotIn("UNAUTHORIZED_LATE_IMPORT", result.stdout)
        result = self.run_python(
            "dt_shell_release.verify_installation(); from dt_shell.commands import DTCommandAbs\n"
            "descriptor = Mock(); descriptor.command.fake = False\n"
            "exec('class Probe(DTCommandAbs):\\n @classmethod\\n"
            " def get_command(cls, shell, line): return descriptor, []\\n')\n"
            f"with patch('time.time', return_value={time.time() + 7200!r}):\n Probe.do_command(Mock(), '')\n",
            overrides={"DTSHELL_PYTHONPATH": str(extra)},
        )
        self.assert_blocked(result, "Developer authorization expired")

    def test_unsigned_commands_and_pythonpath_execute_only_in_authenticated_mode(self):
        self.cache()
        commands = self.source_commands(extra_import=True)
        helpers = self.home / "helpers"
        helpers.mkdir()
        (helpers / "developer_extra.py").write_text(
            "print('AUTHORIZED_PYTHONPATH_LOADED')\n", encoding="ascii"
        )
        result = self.run_python(
            "dt_shell_release.delegated_main()",
            overrides={
                "DTSHELL_COMMANDS": str(commands),
                "DTSHELL_PYTHONPATH": str(helpers),
            },
            extra={"IGNORE_ENVIRONMENTS": "1"},
            arguments=("probe",),
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("AUTHORIZED_COMMAND_EXECUTED", result.stdout)
        self.assertIn("AUTHORIZED_PYTHONPATH_LOADED", result.stdout)
        self.cache(self.grant(key=Ed25519PrivateKey.generate()))
        blocked = self.run_python(
            "dt_shell_release.delegated_main()",
            overrides={
                "DTSHELL_COMMANDS": str(commands),
                "DTSHELL_PYTHONPATH": str(helpers),
            },
            extra={"IGNORE_ENVIRONMENTS": "1"},
            arguments=("probe",),
        )
        self.assert_blocked(blocked, "signature is invalid")
        self.assertNotIn("AUTHORIZED_PYTHONPATH_LOADED", blocked.stdout)
        self.assertNotIn("AUTHORIZED_COMMAND_EXECUTED", blocked.stdout)

    def test_source_override_changes_and_identity_switches_require_reauthorization(
        self,
    ):
        self.cache()
        helpers = self.home / "helpers"
        helpers.mkdir()
        result = self.run_python(
            "dt_shell_release.verify_installation(); import os\n"
            "os.environ['DTSHELL_PYTHONPATH'] = os.environ['DTSHELL_PROFILES']\n"
            "dt_shell_release.verify_installation()\n",
            overrides={"DTSHELL_PYTHONPATH": str(helpers)},
        )
        self.assert_blocked(result, "overrides changed")
        result = self.run_python(
            "dt_shell_release.verify_installation(); from pathlib import Path\n"
            f"Path({str(self.profile / 'databases/secrets.yaml')!r}).write_text("
            '"version: 1\\ndata: {}\\n")\n'
            "dt_shell_release.verify_installation()\n",
            overrides={"DTSHELL_PYTHONPATH": str(helpers)},
        )
        self.assert_blocked(result, "requires a DT2")

    def test_library_commands_and_pythonpath_work_together_without_runtime_cython(self):
        self.cache()
        commands = self.source_commands(extra_import=True)
        helpers = self.home / "helpers"
        helpers.mkdir()
        (helpers / "developer_extra.py").write_text(
            "print('AUTHORIZED_PYTHONPATH_LOADED')\n", encoding="ascii"
        )
        source = Path(__file__).resolve().parents[1]
        result = self.run_python(
            "import importlib.abc\n"
            "class NoCython(importlib.abc.MetaPathFinder):\n"
            " def find_spec(self, fullname, path=None, target=None):\n"
            "  if fullname == 'cython': raise ModuleNotFoundError(\"Runtime Cython is unavailable\", name='cython')\n"
            "sys.meta_path.insert(0, NoCython())\n"
            "dt_shell_release.delegated_main()\n",
            overrides={
                "DTSHELL_LIB": str(source),
                "DTSHELL_COMMANDS": str(commands),
                "DTSHELL_PYTHONPATH": str(helpers),
            },
            extra={"IGNORE_ENVIRONMENTS": "1"},
            arguments=("probe",),
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("AUTHORIZED_COMMAND_EXECUTED", result.stdout)
        self.assertIn("AUTHORIZED_PYTHONPATH_LOADED", result.stdout)

    def test_empty_paths_remain_invalid_even_with_a_signed_grant(self):
        self.cache()
        for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
            with self.subTest(name=name):
                result = self.run_python(
                    "dt_shell_release.launch()", overrides={name: ""}
                )
                self.assert_blocked(result, "empty override")

    def test_embedded_developer_command_works_with_compiled_and_source_overridden_shells(
        self,
    ):
        self.cache()
        commands = self.source_commands()
        for library in (None, Path(__file__).resolve().parents[1]):
            with self.subTest(library=library):
                overrides = {"DTSHELL_COMMANDS": str(commands)}
                if library is not None:
                    overrides["DTSHELL_LIB"] = str(library)
                result = self.run_python(
                    "dt_shell_release.delegated_main()",
                    overrides=overrides,
                    extra={"IGNORE_ENVIRONMENTS": "1"},
                    arguments=("developer", "status"),
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("Developer grant: valid", result.stdout)

    def test_authenticated_source_delegation_uses_the_verified_native_bootstrap(self):
        self.cache()
        source = Path(__file__).resolve().parents[1]
        result = self.run_python(
            "dt_shell_release.verify_installation(); import os\n"
            "sys.path.insert(0, os.environ['DTSHELL_LIB'])\n"
            "from dt_shell.environments import VirtualPython3Environment\n"
            "from dt_shell.integrity import is_release_build, is_developer_mode\n"
            "assert not is_release_build() and is_developer_mode()\n"
            "shell = Mock(command_sets=[]); cache = Mock(); cache.needs_install_step.return_value = False\n"
            "os.environ['DTSHELL_VENV_DIR'] = sys.prefix\n"
            "with patch('dt_shell.environments.InstalledDependenciesDatabase.load', return_value=cache), "
            "patch('dt_shell.environments.os.execle') as delegated:\n"
            " VirtualPython3Environment().execute(shell, [])\n"
            "arguments = delegated.call_args.args\n"
            "assert 'module.delegated_main()' in arguments[3]\n"
            "assert repr(dt_shell_release.__file__) in arguments[3]\n"
            "assert 'PYTHONPATH' not in arguments[-1]\n",
            overrides={"DTSHELL_LIB": str(source)},
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
