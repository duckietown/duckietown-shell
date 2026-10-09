import datetime
from typing import List

from dt_shell import DTCommandAbs, DTShell, UserError
from dt_shell.authorization import (
    ENTE_ACCESS_PLAN_NAMES,
    format_plan_names,
    format_utc_datetime,
    get_ente_status,
)


class DTCommand(DTCommandAbs):
    @staticmethod
    def command(shell: DTShell, args: List[str]):
        if args:
            raise UserError("Usage: dts subscription status")
        status = get_ente_status(shell)
        shell.sprint(f"Account plans: {format_plan_names(status['plan'])}")
        if status["exempt"]:
            shell.sprint("Plan requirement for 'ente': waived (staff or superuser account)")
        else:
            shell.sprint(f"Plan requirement for 'ente': {'met' if status['eligible'] else 'not met'}")
            base_plan = status["base_plan"]
            if base_plan is None:
                shell.sprint("Plan granting 'ente' access: none active")
                shell.sprint(
                    "Required plan: the free 'Independent User' plan or the 'Institutional User' plan."
                )
            else:
                plan = format_plan_names(ENTE_ACCESS_PLAN_NAMES[base_plan])
                shell.sprint(f"Plan granting 'ente' access: {plan}")
                end = status["entitlement_expiration"]
                deadline = (
                    format_utc_datetime(datetime.datetime.fromtimestamp(end, datetime.timezone.utc))
                    if end is not None
                    else "no expiration recorded"
                )
                shell.sprint(f"Plan expiration: {deadline}")
        device = status.get("device")
        computer = (
            f"'{device['hostname']}'"
            if device is not None
            else "not required for this account"
            if status["exempt"]
            else "none"
        )
        shell.sprint(f"Registered computer: {computer}")
        pending = status.get("pending_device")
        if pending is not None:
            available_at = format_utc_datetime(
                datetime.datetime.fromisoformat(status["transfer_available_at"])
            )
            shell.sprint(f"Pending transfer: to '{pending['hostname']}'")
            shell.sprint(f"Transfer available from: {available_at}")
            shell.sprint("New authorizations are paused until the transfer completes.")
        if status.get("authorization_expiration") is not None:
            expiration = format_utc_datetime(
                datetime.datetime.fromisoformat(status["authorization_expiration"])
            )
            shell.sprint(f"Existing computer authorizations expire by: {expiration}")
        shell.sprint(
            "The 'Instructor' plan is an add-on to the 'Institutional User' plan; "
            "it does not grant 'ente' access by itself."
        )
        shell.sprint("The 'daffy' distribution does not require a plan.")
