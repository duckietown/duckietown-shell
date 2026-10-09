import datetime
import hashlib
import math
import time
from typing import Dict, Optional, Tuple, TYPE_CHECKING

import requests
from dt_authentication import DuckietownToken, ExpiredToken, InvalidToken

from . import logger
from .constants import DB_ENTE_AUTHORIZATION, DTHUB_URL, EMBEDDED_COMMAND_SET_NAME
from .device import get_device_id, get_device_parameters
from .exceptions import UserError

if TYPE_CHECKING:
    from .commands import CommandDescriptor
    from .shell import DTShell


ENTE_AUTHORIZATION_MAX_AGE = 24 * 60 * 60
ENTE_ACCESS_PLAN_NAMES = {
    "independent_user": "Independent User",
    "institutional_user": "Institutional User",
}


def format_plan_names(value: str) -> str:
    if value == "None":
        return "none"
    return ", ".join(f"'{name}' plan" for name in value.split(" + "))


def format_utc_datetime(value: datetime.datetime) -> str:
    if value.utcoffset() is None:
        raise UserError("The Hub returned a date without a time zone.")
    value = value.astimezone(datetime.timezone.utc)
    clock_format = "%H:%M:%S" if value.second or value.microsecond else "%H:%M"
    return value.strftime(f"%d %B %Y at {clock_format} UTC")


def _validate_authorization(value: str, uid: int) -> dict:
    token = DuckietownToken.from_string(value, allow_expired=False)
    data = token.data
    if (
        token.version != "dt2"
        or token.uid != uid
        or token.expiration is None
        or token.renewable
        or not token.grants("use", "ente")
        or not isinstance(data, dict)
        or not {
            "authorization_version",
            "plan",
            "base_plan",
            "device_id",
            "is_staff",
            "is_superuser",
            "entitlement_expiration",
        }.issubset(data)
        or data.get("hub") != DTHUB_URL
        or data.get("authorization_version") != 2
        or not isinstance(data.get("plan"), str)
        or not data["plan"]
        or not isinstance(data.get("is_staff"), bool)
        or not isinstance(data.get("is_superuser"), bool)
    ):
        raise UserError("The Hub returned an invalid authorization for 'ente'.")
    exempt = data["is_staff"] or data["is_superuser"]
    if not exempt:
        if (
            not isinstance(data.get("base_plan"), str)
            or data["base_plan"] not in ENTE_ACCESS_PLAN_NAMES
            or data["plan"] in ("", "None")
            or data.get("device_id") != get_device_id()
        ):
            raise UserError("This 'ente' authorization does not match your plan or this computer.")
    end = data.get("entitlement_expiration")
    if end is not None:
        if isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end):
            raise UserError("The Hub returned an invalid plan-expiration date.")
        try:
            deadline = datetime.datetime.fromtimestamp(end, datetime.timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError) as error:
            raise UserError("The Hub returned an invalid plan-expiration date.") from error
        if token.expiration > deadline:
            raise UserError(
                "The 'ente' authorization extends beyond the expiration of the plan granting access."
            )
    return data


def _identity(shell: "DTShell") -> Tuple[str, DuckietownToken]:
    profile = shell.profile
    if profile is None or profile.distro is None:
        raise UserError("Select a DTS profile and distribution before running this command.")
    identity = profile.secrets.dt_token
    if not isinstance(identity, str):
        raise UserError("Set a Duckietown Token with 'dts tok set' before using the 'ente' distribution.")
    try:
        identity_token = DuckietownToken.from_string(identity, allow_expired=False)
    except (InvalidToken, ExpiredToken, ValueError) as e:
        raise UserError(
            "Your Duckietown Token is invalid or expired. Set a valid DT2 token with 'dts tok set'."
        ) from e
    if identity_token.version != "dt2":
        raise UserError("The 'ente' distribution requires a DT2 Duckietown Token. Use 'dts tok set'.")
    if not identity_token.grants("auth"):
        raise UserError(
            "Set a DT2 identity token with 'dts tok set'; an authorization token cannot identify your account."
        )
    return identity, identity_token


def _request(
    identity: str,
    suffix: str = "",
    values: Optional[Dict[str, str]] = None,
    *,
    post: bool = False,
) -> dict:
    try:
        url = f"{DTHUB_URL}/api/v1/auth/token/ente/{suffix}"
        headers = {"Authorization": f"Token {identity}"}
        if post:
            response = requests.post(url, json=values, headers=headers, timeout=(5, 10))
        elif values is not None:
            response = requests.get(url, params=values, headers=headers, timeout=(5, 10))
        else:
            response = requests.get(url, headers=headers, timeout=(5, 10))
        response.raise_for_status()
    except requests.RequestException as e:
        raise UserError(
            f"Could not complete the request to Duckietown Hub at {DTHUB_URL}: {e}.\n"
            "The 'ente' distribution requires a valid cached authorization when the Hub is unavailable. "
            "The 'daffy' distribution does not require a plan."
        ) from e
    try:
        payload = response.json()
    except ValueError as e:
        raise UserError("The Hub returned invalid JSON for this subscription request.") from e
    if not isinstance(payload, dict):
        raise UserError("The Hub returned an invalid subscription response.")
    return payload


def _result(payload: dict) -> dict:
    if payload.get("success") is not True:
        messages = payload.get("messages")
        if not isinstance(messages, list) or not all(isinstance(message, str) for message in messages):
            raise UserError("The Hub returned an invalid subscription response.")
        reason = " ".join(messages).strip() or "The Hub did not authorize this request."
        raise UserError(reason)

    result = payload.get("result")
    if not isinstance(result, dict):
        raise UserError("The Hub returned an invalid subscription response.")
    return result


def require_ente_plan(shell: "DTShell", command: "CommandDescriptor") -> None:
    if command.command_set.name == EMBEDDED_COMMAND_SET_NAME:
        return
    profile = shell.profile
    if profile is None or profile.distro is None:
        raise UserError("Select a DTS profile and distribution before running this command.")
    if profile.distro.name != "ente":
        return
    identity, identity_token = _identity(shell)
    cache = profile.database(DB_ENTE_AUTHORIZATION)
    key = f"{DTHUB_URL}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"
    entry = cache.get(key, None)
    if entry is not None:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("checked_at"), (int, float))
            and isinstance(entry.get("token"), str)
        ):
            age = time.time() - entry["checked_at"]
            if 0 <= age < ENTE_AUTHORIZATION_MAX_AGE:
                try:
                    _validate_authorization(entry["token"], identity_token.uid)
                except ExpiredToken:
                    pass
                except (InvalidToken, ValueError, UserError) as error:
                    logger.warning(f"Discarding an invalid cached 'ente' authorization: {error}")
                else:
                    return
        else:
            logger.warning("Discarding a cached 'ente' authorization with invalid cache data.")
        cache.delete(key)
    payload = _request(identity)
    if (
        payload.get("success") is False
        and payload.get("code") == 428
        and isinstance(payload.get("result"), dict)
        and payload["result"].get("reason") == "device_required"
    ):
        payload = _request(identity, values=get_device_parameters())
    result = _result(payload)
    if not isinstance(result.get("token"), str):
        raise UserError("The Hub did not return an authorization token for 'ente'.")
    authorization = result["token"]
    try:
        data = _validate_authorization(authorization, identity_token.uid)
    except (InvalidToken, ExpiredToken, ValueError) as e:
        raise UserError("The Hub returned an invalid or expired authorization for 'ente'.") from e
    cache.set(key, {"token": authorization, "checked_at": time.time()})
    end = data.get("entitlement_expiration")
    if end is not None and 0 < end - time.time() <= 3 * 24 * 60 * 60:
        deadline = format_utc_datetime(datetime.datetime.fromtimestamp(end, datetime.timezone.utc))
        logger.warning(
            f"The plan granting 'ente' access expires on {deadline}. "
            f"View or change your plans at {DTHUB_URL}/plans/"
        )


def get_ente_status(shell: "DTShell") -> dict:
    identity, _ = _identity(shell)
    result = _result(_request(identity, "status/"))
    if (
        not {
            "plan",
            "eligible",
            "exempt",
            "base_plan",
            "entitlement_expiration",
            "device",
            "pending_device",
            "transfer_available_at",
            "authorization_expiration",
        }.issubset(result)
        or not isinstance(result.get("plan"), str)
        or not result["plan"].strip()
        or not isinstance(result.get("eligible"), bool)
        or not isinstance(result.get("exempt"), bool)
        or result.get("base_plan") not in (None, "independent_user", "institutional_user")
    ):
        raise UserError("The Hub returned an invalid subscription-status response.")
    end = result.get("entitlement_expiration")
    if end is not None and (
        isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end)
    ):
        raise UserError("The Hub returned an invalid plan-expiration date.")
    if end is not None:
        try:
            datetime.datetime.fromtimestamp(end, datetime.timezone.utc)
        except (ValueError, OverflowError, OSError) as error:
            raise UserError("The Hub returned an invalid plan-expiration date.") from error
    for field in ("device", "pending_device"):
        value = result.get(field)
        if value is not None and (
            not isinstance(value, dict)
            or not isinstance(value.get("hostname"), str)
            or not isinstance(value.get("device_id"), str)
        ):
            raise UserError("The Hub returned invalid computer-registration details.")
    for field in ("transfer_available_at", "authorization_expiration"):
        value = result.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise UserError("The Hub returned an invalid authorization or transfer date.")
            try:
                date = datetime.datetime.fromisoformat(value)
            except ValueError as error:
                raise UserError("The Hub returned an invalid authorization or transfer date.") from error
            if date.tzinfo is None:
                raise UserError("The Hub returned an authorization or transfer date without a time zone.")
    if result["pending_device"] is not None and result["transfer_available_at"] is None:
        raise UserError("The Hub returned incomplete computer-transfer details.")
    return result


def transfer_ente_device(shell: "DTShell") -> str:
    status = get_ente_status(shell)
    if status["exempt"]:
        return (
            "Your account is exempt from computer registration for 'ente' as staff or a superuser. "
            "No transfer is needed."
        )
    identity, _ = _identity(shell)
    response = _request(identity, "transfer/", get_device_parameters(), post=True)
    result = _result(response)
    available_at = result.get("available_at")
    if not isinstance(available_at, str):
        raise UserError("The Hub returned an invalid transfer-availability date.")
    try:
        date = datetime.datetime.fromisoformat(available_at)
    except ValueError as error:
        raise UserError("The Hub returned an invalid transfer-availability date.") from error
    if date.tzinfo is None:
        raise UserError("The Hub returned a transfer-availability date without a time zone.")
    messages = response.get("messages")
    if (
        not isinstance(messages, list)
        or not messages
        or not all(isinstance(message, str) and message.strip() for message in messages)
    ):
        raise UserError("The Hub returned an invalid computer-registration confirmation.")
    return "\n".join(messages)
