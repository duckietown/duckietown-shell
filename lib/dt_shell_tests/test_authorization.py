from contextlib import contextmanager, ExitStack
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests
from ecdsa import SigningKey

from dt_authentication import DuckietownToken
from dt_authentication.token import CURVE, DATETIME_FORMAT, PUBLIC_KEYS
from dt_shell.authorization import (
    ENTE_AUTHORIZATION_MAX_AGE,
    ENTE_PLAN_ENFORCEMENT_START,
    format_utc_datetime,
    get_ente_status,
    require_ente_plan,
    transfer_ente_device,
)
from dt_shell import DTShell
from dt_shell.commands import CommandSet, FailedToLoadCommand
from dt_shell.commands.importer import import_command
from dt_shell.constants import DTHUB_URL, EMBEDDED_COMMAND_SET_NAME, KNOWN_DISTRIBUTIONS, SHELL_LIB_DIR
from dt_shell.embedded.plan.status.command import DTCommand as PlanStatusCommand
from dt_shell.embedded.plan.transfer.command import DTCommand as PlanTransferCommand
from dt_shell.exceptions import CommandNotFound, UserError
from dt_shell.profile import ShellProfile


class EmbeddedPlanCommandsTests(unittest.TestCase):
    def status_output(self, **values):
        shell = Mock()
        status = {
            "plan": "Independent User",
            "eligible": True,
            "exempt": False,
            "base_plan": "independent_user",
            "entitlement_expiration": None,
            "device": {"device_id": "a" * 64, "hostname": "computer-a"},
            "pending_device": None,
            "transfer_available_at": None,
            "authorization_expiration": "2026-10-10T14:38:00+00:00",
            **values,
        }
        with patch("dt_shell.embedded.plan.status.command.get_ente_status", return_value=status):
            PlanStatusCommand.command(shell, [])
        return "\n".join(call.args[0] for call in shell.sprint.call_args_list)

    def test_plan_commands_load_through_the_existing_importer(self):
        embedded_path = Path(SHELL_LIB_DIR) / "embedded"
        command_set = Mock(path=str(embedded_path))
        with patch("sys.path", [str(embedded_path), *sys.path]), patch.dict("sys.modules"):
            for name in ("status", "transfer"):
                with self.subTest(command=name):
                    command = import_command(command_set, str(embedded_path / "plan" / name))
                    self.assertIsNot(command, FailedToLoadCommand)
                    self.assertEqual(f"plan.{name}.command", command.__module__)

    def test_plan_commands_are_discovered_and_dispatched_without_old_aliases(self):
        embedded_path = Path(SHELL_LIB_DIR) / "embedded"
        profile = Mock(command_descriptions={})
        ShellProfile.update_command_descriptions(profile, str(embedded_path))
        command_set = CommandSet(EMBEDDED_COMMAND_SET_NAME, str(embedded_path), profile, leave_alone=True)
        self.assertIn("plan", command_set.commands)
        self.assertNotIn("subscription", command_set.commands)
        self.assertIn("plan", profile.command_descriptions)
        self.assertNotIn("subscription", profile.command_descriptions)
        self.assertEqual({"status", "transfer"}, set(profile.command_descriptions["plan"]["subcommands"]))
        shell = DTShell.__new__(DTShell)
        shell._profile = profile
        shell._errors_loading = []
        with ExitStack() as stack:
            stack.enter_context(patch("sys.path", [str(embedded_path), *sys.path]))
            stack.enter_context(patch.dict("sys.modules"))
            stack.enter_context(patch.object(DTShell, "include", SimpleNamespace(), create=True))
            for prefix in ("do_", "get_", "complete_", "help_"):
                stack.enter_context(patch.object(DTShell, prefix + "plan", create=True))
            shell._load_command_subtree(command_set, "", "plan", command_set.commands["plan"], 0, False)
            self.assertEqual([], shell._errors_loading)
            for name in ("status", "transfer"):
                self.assertEqual(f"plan.{name}", shell.get_command(f"plan {name}").selector)
                with self.assertRaises(CommandNotFound):
                    shell.get_command(f"subscription {name}")
            self.assertEqual(
                {"status", "transfer"},
                set(shell.complete_plan("", "plan ", 5, 5)),
            )

    def test_plan_usage_messages_reject_extra_arguments_before_contacting_hub(self):
        shell = Mock()
        with patch("dt_shell.embedded.plan.status.command.get_ente_status") as status, patch(
            "dt_shell.embedded.plan.transfer.command.transfer_ente_device"
        ) as transfer:
            for name, command in (("status", PlanStatusCommand), ("transfer", PlanTransferCommand)):
                with self.subTest(command=name), self.assertRaisesRegex(
                    UserError, f"^Usage: dts plan {name}$"
                ):
                    command.command(shell, ["unexpected"])
            status.assert_not_called()
            transfer.assert_not_called()
        shell.sprint.assert_not_called()

    def test_plan_transfer_reports_the_existing_confirmation(self):
        shell = Mock()
        confirmation = "This computer is already registered for 'ente'. No transfer is needed."
        with patch(
            "dt_shell.embedded.plan.transfer.command.transfer_ente_device",
            return_value=confirmation,
        ) as transfer:
            PlanTransferCommand.command(shell, [])
        transfer.assert_called_once_with(shell)
        shell.sprint.assert_called_once_with(confirmation)

    def test_status_distinguishes_plan_expiration_from_issued_authorization_expiration(self):
        authorization_expiration = "2026-10-10T14:38:00+00:00"
        plan_expiration = datetime.datetime(2026, 10, 12, 14, 38, tzinfo=datetime.timezone.utc)
        for plan, base_plan, end, expected in (
            ("Independent User", "independent_user", None, "no expiration recorded"),
            (
                "Institutional User",
                "institutional_user",
                plan_expiration.timestamp(),
                "12 October 2026 at 14:38 UTC",
            ),
        ):
            with self.subTest(plan=plan):
                output = self.status_output(
                    plan=plan,
                    base_plan=base_plan,
                    entitlement_expiration=end,
                    authorization_expiration=authorization_expiration,
                )
                self.assertIn(f"Account plans: '{plan}' plan", output)
                self.assertIn(f"Plan granting 'ente' access: '{plan}' plan", output.splitlines())
                self.assertIn(f"Plan expiration: {expected}", output)
                self.assertIn(
                    "Existing computer authorizations expire by: 10 October 2026 at 14:38 UTC", output
                )
                self.assertIn("Plan requirement for 'ente': met", output)
                self.assertNotIn("paid", output.lower())
                self.assertNotIn(authorization_expiration, output)
                self.assertNotIn("base plan", output.lower())
                self.assertNotIn("base-plan", output.lower())
                self.assertNotRegex(output, r"\b(?:Ente|Daffy)\b")
                self.assertNotIn("(free)", output)

    def test_account_plans_include_add_on_but_access_is_granted_by_the_institutional_plan(self):
        output = self.status_output(plan="Institutional User + Instructor", base_plan="institutional_user")
        self.assertIn("Account plans: 'Institutional User' plan, 'Instructor' plan", output)
        self.assertIn("Plan granting 'ente' access: 'Institutional User' plan", output)
        for name in ("Institutional User", "Instructor"):
            self.assertEqual(output.count(name), output.count(f"'{name}' plan"))

    def test_no_plan_and_instructor_only_status_explain_the_requirement(self):
        for plan, displayed in (("None", "none"), ("Instructor", "'Instructor' plan")):
            with self.subTest(plan=plan):
                output = self.status_output(
                    plan=plan,
                    eligible=False,
                    base_plan=None,
                    device=None,
                    authorization_expiration=None,
                )
                self.assertIn(f"Account plans: {displayed}", output)
                self.assertIn("Plan requirement for 'ente': not met", output)
                self.assertIn("Plan granting 'ente' access: none active", output)
                self.assertIn("free 'Independent User' plan or the 'Institutional User' plan", output)
                self.assertIn("The 'daffy' distribution does not require a plan.", output)
                self.assertNotIn("Plan expiration:", output)

    def test_staff_status_waives_plan_and_computer_requirements(self):
        output = self.status_output(
            plan="None",
            exempt=True,
            base_plan=None,
            device=None,
            authorization_expiration=None,
        )
        self.assertIn("Plan requirement for 'ente': waived", output)
        self.assertIn("Registered computer: not required for this account", output)
        self.assertNotIn("Plan expiration:", output)
        self.assertNotIn("Plan granting 'ente' access: none active", output)

    def test_pending_transfer_dates_are_readable_and_converted_to_utc(self):
        output = self.status_output(
            pending_device={"device_id": "b" * 64, "hostname": "replacement"},
            transfer_available_at="2026-10-10T16:38:00+02:00",
            authorization_expiration="2026-10-10T10:38:05-04:00",
        )
        self.assertIn("Pending transfer: to 'replacement'", output)
        self.assertIn("Transfer available from: 10 October 2026 at 14:38 UTC", output)
        self.assertIn("10 October 2026 at 14:38:05 UTC", output)
        self.assertNotIn("2026-10-10T", output)

    def test_date_formatting_keeps_utc_date_boundaries_and_rejects_naive_dates(self):
        self.assertEqual(
            "31 December 2026 at 23:05 UTC",
            format_utc_datetime(datetime.datetime.fromisoformat("2027-01-01T01:05:00+02:00")),
        )
        with self.assertRaisesRegex(UserError, "without a time zone"):
            format_utc_datetime(datetime.datetime(2026, 10, 10, 14, 38))

    def test_grace_status_shows_the_deadline_instead_of_claiming_the_plan_requirement_is_met(self):
        output = self.status_output(
            plan="None",
            base_plan=None,
            grace_period=True,
            plan_required_from=ENTE_PLAN_ENFORCEMENT_START.isoformat(),
        )
        self.assertIn("starts on 01 February 2027 at 00:00 UTC (grace period)", output)
        self.assertIn("Plan granting 'ente' access: none active", output)
        self.assertNotIn("Plan requirement for 'ente': met", output)
        self.assertIn("free 'Independent User' plan", output)


class EnteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.signing_key = SigningKey.generate(curve=CURVE)
        self.keys = patch.dict(
            PUBLIC_KEYS,
            {version: self.signing_key.verifying_key.to_pem().decode() for version in ("dt1", "dt2")},
        )
        self.keys.start()
        self.addCleanup(self.keys.stop)
        self.identity = DuckietownToken.generate(
            self.signing_key, 123, days=7, scope=["auth"], version="dt2"
        ).as_string()
        self.shell = Mock()
        self.shell.profile.distro = KNOWN_DISTRIBUTIONS["ente"]
        self.shell.profile.secrets.dt_token = self.identity
        self.cache_data = {}
        self.cache = self.shell.profile.database.return_value
        self.cache.get.side_effect = self.cache_data.get
        self.cache.set.side_effect = self.cache_data.__setitem__
        self.cache.delete.side_effect = lambda key: self.cache_data.pop(key, None)
        self.command = Mock()
        self.command.command_set.name = "development"
        self.device_patch = patch("dt_shell.authorization.get_device_id", return_value="a" * 64)
        self.device = self.device_patch.start()
        self.addCleanup(self.device_patch.stop)
        self.parameters_patch = patch(
            "dt_shell.authorization.get_device_parameters",
            return_value={"device_id": "a" * 64, "device_hostname": "computer-a"},
        )
        self.parameters = self.parameters_patch.start()
        self.addCleanup(self.parameters_patch.stop)
        self.http = patch("dt_shell.authorization.requests.get")
        self.get = self.http.start()
        self.addCleanup(self.http.stop)
        self.response = self.get.return_value
        self.response.json.return_value = self.success_response()

    def grant(self, *, uid=123, scope=None, data=None, hours=24, renewable=False, expiration=None):
        token = DuckietownToken.generate(
            self.signing_key,
            uid,
            hours=hours,
            scope=scope if scope is not None else ["use:ente"],
            data=data if data is not None else self.claims(),
            renewable=renewable,
            version="dt2",
        )
        if expiration is not None:
            payload = token.payload
            payload["exp"] = expiration.strftime(DATETIME_FORMAT["dt2"])
            signature = self.signing_key.sign(json.dumps(payload, sort_keys=True).encode())
            token = DuckietownToken("dt2", payload, signature)
        return token.as_string()

    @contextmanager
    def grace_clock(self, now):
        with patch("dt_authentication.token.datetime", wraps=datetime) as clock, patch(
            "dt_shell.authorization.time.time", return_value=now.timestamp()
        ) as wall:
            clock.datetime.utcnow.return_value = now.replace(tzinfo=None)
            self.identity = DuckietownToken.generate(
                self.signing_key, 123, days=7, scope=["auth"], version="dt2"
            ).as_string()
            self.shell.profile.secrets.dt_token = self.identity
            yield clock, wall

    def claims(self, **values):
        return {
            "authorization_version": 2,
            "plan": "Independent User",
            "base_plan": "independent_user",
            "hub": DTHUB_URL,
            "device_id": "a" * 64,
            "is_staff": False,
            "is_superuser": False,
            "entitlement_expiration": None,
            **values,
        }

    def success_response(self, token=None):
        return {"success": True, "result": {"token": token or self.grant()}}

    def cache_key(self):
        return f"{DTHUB_URL}:{hashlib.sha256(self.identity.encode()).hexdigest()}"

    def test_daffy_does_not_check_plan_or_identity(self):
        for distro in ("daffy", "daffy-staging"):
            with self.subTest(distro=distro):
                self.shell.profile.distro = KNOWN_DISTRIBUTIONS[distro]
                self.shell.profile.secrets.dt_token = None
                require_ente_plan(self.shell, self.command)
        self.get.assert_not_called()
        self.shell.profile.database.assert_not_called()

    def test_embedded_management_commands_remain_available(self):
        self.command.command_set.name = EMBEDDED_COMMAND_SET_NAME
        self.shell.profile = None
        require_ente_plan(self.shell, self.command)
        self.get.assert_not_called()

    def test_missing_profile_is_reported(self):
        self.shell.profile = None
        with self.assertRaisesRegex(UserError, "Select a DTS profile"):
            require_ente_plan(self.shell, self.command)
        self.get.assert_not_called()

    def test_missing_invalid_and_wrong_version_identity_is_denied(self):
        dt1 = DuckietownToken.generate(self.signing_key, 123, days=7, version="dt1").as_string()
        for identity in (None, "invalid", dt1):
            with self.subTest(identity=identity):
                self.shell.profile.secrets.dt_token = identity
                with self.assertRaises(UserError):
                    require_ente_plan(self.shell, self.command)
        self.get.assert_not_called()

    def test_authorized_ente_and_staging_cache_a_signed_grant(self):
        for distro in ("ente", "ente-staging"):
            with self.subTest(distro=distro):
                self.cache_data.clear()
                self.shell.profile.distro = KNOWN_DISTRIBUTIONS[distro]
                require_ente_plan(self.shell, self.command)
                self.assertIn(self.cache_key(), self.cache_data)
        self.get.assert_called_with(
            f"{DTHUB_URL}/api/v1/auth/token/ente/",
            headers={"Authorization": f"Token {self.identity}"},
            timeout=(5, 10),
        )

    def test_no_plan_denies_without_caching(self):
        self.response.json.return_value = {
            "success": False,
            "code": 403,
            "messages": ["Your account has no active plan granting access to 'ente'."],
            "result": {"plan": "None"},
        }
        with self.assertRaisesRegex(UserError, "no active plan"):
            require_ente_plan(self.shell, self.command)
        self.assertEqual({}, self.cache_data)

    def test_valid_cache_avoids_another_hub_request(self):
        require_ente_plan(self.shell, self.command)
        self.get.reset_mock()
        self.get.side_effect = requests.ConnectionError("offline")
        require_ente_plan(self.shell, self.command)
        self.get.assert_not_called()

    def test_cache_refreshes_at_exactly_twenty_four_hours(self):
        now = time.time()
        with patch("dt_shell.authorization.time.time", return_value=now):
            require_ente_plan(self.shell, self.command)
        self.get.reset_mock()
        for age, expected_requests in (
            (ENTE_AUTHORIZATION_MAX_AGE - 1, 0),
            (ENTE_AUTHORIZATION_MAX_AGE, 1),
        ):
            with self.subTest(age=age):
                self.get.reset_mock()
                with patch("dt_shell.authorization.time.time", return_value=now + age):
                    require_ente_plan(self.shell, self.command)
                self.assertEqual(expected_requests, self.get.call_count)

    def test_expired_signed_grant_is_refreshed_even_with_recent_check(self):
        value = DuckietownToken.from_string(self.grant()).payload
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        value["exp"] = (now - datetime.timedelta(seconds=1)).strftime(DATETIME_FORMAT["dt2"])
        value["scope"] = [scope.compact() for scope in value["scope"]]
        signature = self.signing_key.sign(json.dumps(value, sort_keys=True).encode())
        expired = DuckietownToken("dt2", value, signature).as_string()
        self.cache_data[self.cache_key()] = {"token": expired, "checked_at": time.time()}
        require_ente_plan(self.shell, self.command)
        self.get.assert_called_once()
        self.assertNotEqual(expired, self.cache_data[self.cache_key()]["token"])

    def test_malformed_tampered_and_future_dated_cache_is_refreshed(self):
        for entry in (
            "bad cache",
            {"token": "invalid", "checked_at": time.time()},
            {"token": self.grant(), "checked_at": time.time() + 60},
        ):
            with self.subTest(entry=entry):
                self.cache_data[self.cache_key()] = entry
                self.get.reset_mock()
                require_ente_plan(self.shell, self.command)
                self.get.assert_called_once()

    def test_changing_identity_or_hub_does_not_reuse_a_grant(self):
        require_ente_plan(self.shell, self.command)
        self.get.reset_mock()
        self.get.side_effect = requests.ConnectionError("offline")
        self.shell.profile.secrets.dt_token = DuckietownToken.generate(
            self.signing_key, 456, days=7, scope=["auth"], version="dt2"
        ).as_string()
        with self.assertRaisesRegex(UserError, "Could not complete the request"):
            require_ente_plan(self.shell, self.command)
        self.shell.profile.secrets.dt_token = self.identity
        with patch("dt_shell.authorization.DTHUB_URL", "https://another-hub.example"):
            with self.assertRaisesRegex(UserError, "Could not complete the request"):
                require_ente_plan(self.shell, self.command)

    def test_network_failure_without_valid_cache_fails_closed(self):
        self.get.side_effect = requests.Timeout("unavailable")
        with self.assertRaisesRegex(UserError, "'daffy' distribution does not require a plan"):
            require_ente_plan(self.shell, self.command)
        self.assertEqual({}, self.cache_data)

    def test_revoked_plan_after_cache_expiry_is_denied(self):
        self.cache_data[self.cache_key()] = {
            "token": self.grant(),
            "checked_at": time.time() - ENTE_AUTHORIZATION_MAX_AGE,
        }
        self.response.json.return_value = {
            "success": False,
            "messages": ["Your account has no active plan granting access to 'ente'."],
            "result": {},
        }
        with self.assertRaisesRegex(UserError, "no active plan"):
            require_ente_plan(self.shell, self.command)
        self.assertEqual({}, self.cache_data)

    def test_invalid_hub_responses_are_not_cached(self):
        for payload in (
            None,
            [],
            {"success": "true", "result": {"token": self.grant()}},
            {"success": False, "messages": "denied"},
            {"success": True},
            {"success": True, "result": {"token": None}},
        ):
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                with self.assertRaises(UserError):
                    require_ente_plan(self.shell, self.command)
                self.assertEqual({}, self.cache_data)

    def test_invalid_json_is_reported(self):
        self.response.json.side_effect = ValueError("not JSON")
        with self.assertRaisesRegex(UserError, "invalid JSON for this plan request"):
            require_ente_plan(self.shell, self.command)

    def test_invalid_plan_response_envelopes_use_plan_wording(self):
        for payload in (
            None,
            [],
            {"success": False, "messages": "denied"},
            {"success": True, "result": []},
        ):
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                with self.assertRaisesRegex(UserError, "invalid plan response"):
                    require_ente_plan(self.shell, self.command)
                self.assertEqual({}, self.cache_data)

    def test_invalid_grants_are_not_cached(self):
        for token in (
            "invalid",
            self.identity,
            self.grant(uid=456),
            self.grant(scope=["auth"]),
            self.grant(data={"plan": "None", "hub": DTHUB_URL}),
            self.grant(data={"plan": "", "hub": DTHUB_URL}),
            self.grant(data={"plan": "Independent User", "hub": "https://another-hub.example"}),
            self.grant(hours=0),
            self.grant(renewable=True),
        ):
            with self.subTest(token=token):
                self.response.json.return_value = self.success_response(token)
                with self.assertRaises(UserError):
                    require_ente_plan(self.shell, self.command)
                self.assertEqual({}, self.cache_data)

    def test_device_identity_challenge_is_answered_without_changing_the_identity_token(self):
        challenge = Mock()
        challenge.json.return_value = {
            "success": False,
            "code": 428,
            "messages": ["Computer identity required."],
            "result": {"reason": "device_required"},
        }
        self.get.side_effect = [challenge, self.response]
        require_ente_plan(self.shell, self.command)
        self.assertEqual(2, self.get.call_count)
        self.get.assert_called_with(
            f"{DTHUB_URL}/api/v1/auth/token/ente/",
            params={"device_id": "a" * 64, "device_hostname": "computer-a"},
            headers={"Authorization": f"Token {self.identity}"},
            timeout=(5, 10),
        )
        self.assertEqual(self.identity, self.shell.profile.secrets.dt_token)

    def test_copied_cache_cannot_authorize_another_computer(self):
        require_ente_plan(self.shell, self.command)
        self.device.return_value = "b" * 64
        self.get.reset_mock()
        self.response.json.return_value = {
            "success": False,
            "messages": ["One computer is allowed per user."],
            "result": {},
            "code": 409,
        }
        with self.assertRaisesRegex(UserError, "One computer"):
            require_ente_plan(self.shell, self.command)
        self.get.assert_called_once()
        self.assertEqual({}, self.cache_data)

    def test_privileged_grants_do_not_require_base_access_or_a_machine_identity(self):
        for flags in ({"is_staff": True}, {"is_superuser": True}):
            with self.subTest(flags=flags):
                self.cache_data.clear()
                self.device.side_effect = UserError("unsupported machine")
                self.response.json.return_value = self.success_response(
                    self.grant(
                        data=self.claims(plan="None", base_plan=None, device_id=None, **flags),
                    )
                )
                require_ente_plan(self.shell, self.command)
        self.device.assert_not_called()
        self.parameters.assert_not_called()

    def test_instructor_only_legacy_and_wrong_device_grants_are_rejected(self):
        for data in (
            self.claims(plan="Instructor", base_plan=None),
            {"plan": "Independent User", "hub": DTHUB_URL},
            self.claims(device_id="b" * 64),
            self.claims(is_staff="true"),
            self.claims(base_plan=[]),
            self.claims(base_plan={}),
        ):
            with self.subTest(data=data):
                self.response.json.return_value = self.success_response(self.grant(data=data))
                with self.assertRaises(UserError):
                    require_ente_plan(self.shell, self.command)
                self.assertEqual({}, self.cache_data)

    def test_grant_cannot_extend_beyond_signed_plan_expiration(self):
        end = time.time() + 3600
        self.response.json.return_value = self.success_response(
            self.grant(
                data=self.claims(entitlement_expiration=end),
            )
        )
        with self.assertRaisesRegex(UserError, "extends beyond"):
            require_ente_plan(self.shell, self.command)
        self.assertEqual({}, self.cache_data)

    def test_near_expiry_warning_is_shown_only_for_a_fresh_grant(self):
        self.response.json.return_value = self.success_response(
            self.grant(
                hours=1,
                data=self.claims(entitlement_expiration=time.time() + 7200),
            )
        )
        with patch("dt_shell.authorization.logger.warning") as warning:
            require_ente_plan(self.shell, self.command)
            require_ente_plan(self.shell, self.command)
        warning.assert_called_once()
        self.assertIn("plan granting 'ente' access expires", warning.call_args[0][0])
        self.assertIn(" UTC", warning.call_args[0][0])
        self.assertNotIn("paid", warning.call_args[0][0].lower())

    def test_free_independent_plan_without_expiration_does_not_warn(self):
        with patch("dt_shell.authorization.logger.warning") as warning:
            require_ente_plan(self.shell, self.command)
        warning.assert_not_called()

    def test_signed_plan_grace_warns_once_and_allows_a_valid_offline_cache(self):
        now = datetime.datetime(2027, 1, 31, 23, tzinfo=datetime.timezone.utc)
        with self.grace_clock(now), patch("dt_shell.authorization.logger.warning") as warning:
            claims = self.claims(
                plan="None", base_plan=None, plan_grace_until=int(ENTE_PLAN_ENFORCEMENT_START.timestamp())
            )
            self.response.json.return_value = self.success_response(
                self.grant(data=claims, expiration=ENTE_PLAN_ENFORCEMENT_START)
            )
            require_ente_plan(self.shell, self.command)
            self.get.reset_mock()
            self.get.side_effect = requests.ConnectionError("offline")
            require_ente_plan(self.shell, self.command)
            self.get.assert_not_called()
        warning.assert_called_once()
        self.assertIn("01 February 2027 at 00:00 UTC", warning.call_args[0][0])
        self.assertIn("Select a qualifying plan before then.", warning.call_args[0][0])
        self.assertIn(f"{DTHUB_URL}/plans/", warning.call_args[0][0])

    def test_cached_plan_grace_cannot_cross_the_exact_cutoff_even_offline(self):
        before = ENTE_PLAN_ENFORCEMENT_START - datetime.timedelta(seconds=1)
        with self.grace_clock(before) as (clock, wall):
            claims = self.claims(
                plan="None", base_plan=None, plan_grace_until=int(ENTE_PLAN_ENFORCEMENT_START.timestamp())
            )
            self.response.json.return_value = self.success_response(
                self.grant(data=claims, expiration=ENTE_PLAN_ENFORCEMENT_START)
            )
            require_ente_plan(self.shell, self.command)
            self.get.reset_mock()
            self.get.side_effect = requests.ConnectionError("offline")
            for offset in (0, 1):
                now = ENTE_PLAN_ENFORCEMENT_START + datetime.timedelta(seconds=offset)
                clock.datetime.utcnow.return_value = now.replace(tzinfo=None)
                wall.return_value = now.timestamp()
                with self.subTest(offset=offset), self.assertRaisesRegex(UserError, "Could not complete"):
                    require_ente_plan(self.shell, self.command)
                self.assertEqual({}, self.cache_data)

    def test_plan_grace_rejects_wrong_types_overlong_expiry_privileges_and_copied_devices(self):
        now = ENTE_PLAN_ENFORCEMENT_START - datetime.timedelta(hours=1)
        deadline = int(ENTE_PLAN_ENFORCEMENT_START.timestamp())
        changes = (
            {"plan_grace_until": None},
            {"plan_grace_until": True},
            {"plan_grace_until": str(deadline)},
            {"plan_grace_until": float(deadline)},
            {"plan_grace_until": deadline + 1},
            {"is_staff": True},
            {"is_superuser": True},
            {"base_plan": "independent_user"},
            {"entitlement_expiration": deadline},
            {"device_id": "b" * 64},
        )
        with self.grace_clock(now):
            for change in changes:
                with self.subTest(change=change):
                    claims = self.claims(
                        **{"plan": "None", "base_plan": None, "plan_grace_until": deadline, **change}
                    )
                    self.response.json.return_value = self.success_response(
                        self.grant(data=claims, expiration=ENTE_PLAN_ENFORCEMENT_START)
                    )
                    with self.assertRaises(UserError):
                        require_ente_plan(self.shell, self.command)
                    self.assertEqual({}, self.cache_data)
            claims = self.claims(plan="None", base_plan=None, plan_grace_until=deadline)
            self.response.json.return_value = self.success_response(
                self.grant(
                    data=claims, expiration=ENTE_PLAN_ENFORCEMENT_START + datetime.timedelta(minutes=1)
                )
            )
            with self.assertRaisesRegex(UserError, "overlong"):
                require_ente_plan(self.shell, self.command)

    def status(self, **values):
        return {
            "plan": "Independent User",
            "eligible": True,
            "exempt": False,
            "base_plan": "independent_user",
            "entitlement_expiration": None,
            "device": {"device_id": "a" * 64, "hostname": "computer-a"},
            "pending_device": None,
            "transfer_available_at": None,
            "authorization_expiration": None,
            **values,
        }

    def test_status_is_informational_and_does_not_obtain_an_authorization(self):
        self.response.json.return_value = {"success": True, "result": self.status()}
        self.assertTrue(get_ente_status(self.shell)["eligible"])
        self.get.assert_called_with(
            f"{DTHUB_URL}/api/v1/auth/token/ente/status/",
            headers={"Authorization": f"Token {self.identity}"},
            timeout=(5, 10),
        )
        self.cache.set.assert_not_called()
        self.parameters.assert_not_called()

    def test_malformed_status_is_explicitly_rejected(self):
        for status in (
            {},
            self.status(eligible="true"),
            self.status(device={"hostname": None}),
            self.status(authorization_expiration="2026-01-01T00:00:00"),
            self.status(pending_device={"device_id": "b" * 64, "hostname": "b"}),
            self.status(plan_required_from=ENTE_PLAN_ENFORCEMENT_START.isoformat()),
            self.status(grace_period=True),
            self.status(grace_period="true", plan_required_from=ENTE_PLAN_ENFORCEMENT_START.isoformat()),
            self.status(grace_period=True, plan_required_from=ENTE_PLAN_ENFORCEMENT_START.isoformat()),
            self.status(
                plan="None",
                base_plan=None,
                grace_period=True,
                plan_required_from="2027-02-02T00:00:00+00:00",
            ),
        ):
            with self.subTest(status=status):
                self.response.json.return_value = {"success": True, "result": status}
                with self.assertRaises(UserError):
                    get_ente_status(self.shell)

    def test_plan_grace_status_is_explicit_and_does_not_register_a_computer(self):
        self.response.json.return_value = {
            "success": True,
            "result": self.status(
                plan="None",
                base_plan=None,
                grace_period=True,
                device=None,
                plan_required_from=ENTE_PLAN_ENFORCEMENT_START.isoformat(),
            ),
        }
        result = get_ente_status(self.shell)
        self.assertTrue(result["eligible"])
        self.assertTrue(result["grace_period"])
        self.parameters.assert_not_called()
        self.cache.set.assert_not_called()

    def test_invalid_plan_status_response_uses_plan_wording(self):
        self.response.json.return_value = {"success": True, "result": {}}
        with self.assertRaisesRegex(UserError, "invalid plan-status response"):
            get_ente_status(self.shell)

    def test_transfer_uses_the_authenticated_computer_and_only_reports_the_confirmation(self):
        self.response.json.return_value = {"success": True, "result": self.status()}
        with patch("dt_shell.authorization.requests.post") as post:
            date = datetime.datetime.now(datetime.timezone.utc).isoformat()
            confirmation = (
                "This computer is already registered for 'ente'. No transfer is needed. "
                "Existing authorizations are unchanged."
            )
            post.return_value.json.return_value = {
                "success": True,
                "result": {"available_at": date},
                "messages": [confirmation],
            }
            message = transfer_ente_device(self.shell)
            post.assert_called_once_with(
                f"{DTHUB_URL}/api/v1/auth/token/ente/transfer/",
                json={"device_id": "a" * 64, "device_hostname": "computer-a"},
                headers={"Authorization": f"Token {self.identity}"},
                timeout=(5, 10),
            )
        self.assertEqual(confirmation, message)
        self.assertNotIn(date, message)
        self.assertNotIn("Old authorizations must expire first", message)

    def test_transfer_reports_the_hub_reason_for_unchanged_and_pending_computers(self):
        self.response.json.return_value = {"success": True, "result": self.status()}
        for hours, reason in (
            (0, "This computer is already registered for 'ente'. No transfer is needed."),
            (
                24,
                "Transfer to this computer is scheduled for 10 October 2026 at 14:38 UTC.",
            ),
        ):
            with self.subTest(hours=hours), patch("dt_shell.authorization.requests.post") as post:
                date = (
                    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)
                ).isoformat()
                post.return_value.json.return_value = {
                    "success": True,
                    "result": {"available_at": date},
                    "messages": [reason],
                }
                message = transfer_ente_device(self.shell)
                self.assertEqual(reason, message)
                self.assertNotIn(date, message)

    def test_same_computer_transfer_availability_is_not_a_new_authorization_expiration(self):
        expiration = "2026-10-10T14:38:00+00:00"
        available_at = "2026-10-09T14:38:52.812074+00:00"
        self.response.json.return_value = {
            "success": True,
            "result": self.status(authorization_expiration=expiration),
        }
        with patch("dt_shell.authorization.requests.post") as post:
            post.return_value.json.return_value = {
                "success": True,
                "result": {"available_at": available_at},
                "messages": [
                    "This computer is already registered for 'ente'. No transfer is needed. "
                    "Existing authorizations are unchanged."
                ],
            }
            message = transfer_ente_device(self.shell)
        self.assertIn("This computer is already registered for 'ente'. No transfer is needed.", message)
        self.assertIn("Existing authorizations are unchanged.", message)
        self.assertNotIn(available_at, message)
        self.assertNotIn(expiration, message)
        self.assertNotIn("availability", message.lower())
        self.assertNotIn("obtain a new Ente authorization from", message)
        self.cache.set.assert_not_called()

    def test_transfer_rejects_malformed_success_messages(self):
        self.response.json.return_value = {"success": True, "result": self.status()}
        for messages in (None, [], [""], [" "], "This computer is already registered.", [1]):
            with self.subTest(messages=messages), patch("dt_shell.authorization.requests.post") as post:
                post.return_value.json.return_value = {
                    "success": True,
                    "result": {"available_at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                    "messages": messages,
                }
                with self.assertRaisesRegex(UserError, "invalid computer-registration confirmation"):
                    transfer_ente_device(self.shell)

    def test_staff_transfer_does_not_identify_or_register_a_computer(self):
        self.response.json.return_value = {"success": True, "result": self.status(exempt=True)}
        with patch("dt_shell.authorization.requests.post") as post:
            self.assertIn("exempt", transfer_ente_device(self.shell))
        post.assert_not_called()
        self.parameters.assert_not_called()


if __name__ == "__main__":
    unittest.main()
