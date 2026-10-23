import argparse
import base64
import binascii
import datetime
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

cdef extern from "dts_release_key.h":
    const char DTS_RELEASE_PUBLIC_KEY[]
    const char DTS_COMMANDS_PUBLIC_KEY[]
    const char DTS_DEVELOPER_PUBLIC_KEYS[]
    const char DTM_RELEASE_PUBLIC_KEY[]
    const char DTM_RENDERER_PUBLIC_KEYS[]
    const char DTV_RELEASE_PUBLIC_KEY[]
    const char DTV_AUTH_PUBLIC_KEYS[]

cdef object _developer_session = None
cdef object _native_modules = None


def renderer_trust():
    verify_installation()
    return (
        (<bytes>DTM_RELEASE_PUBLIC_KEY).decode("ascii"),
        json.loads((<bytes>DTM_RENDERER_PUBLIC_KEYS).decode("ascii")),
    )


def viewer_trust():
    verify_installation()
    return (
        (<bytes>DTV_RELEASE_PUBLIC_KEY).decode("ascii"),
        json.loads((<bytes>DTV_AUTH_PUBLIC_KEYS).decode("ascii")),
    )


class ReleaseIntegrityError(RuntimeError):
    pass


class DeveloperAuthorizationError(ReleaseIntegrityError):
    pass


class DeveloperGrantExpired(DeveloperAuthorizationError):
    pass


def _developer_failure(detail):
    return DeveloperAuthorizationError(
        f"Developer authorization failed: {detail}\n"
        "Source overrides require a signed staff/superuser developer grant. "
        "Unset DTSHELL_LIB, DTSHELL_COMMANDS, and DTSHELL_PYTHONPATH to use normal DTS. "
        "Manage authorization with 'dts developer status', 'dts developer renew', or 'dts developer clear'."
    )


cdef object _developer_keys():
    return json.loads((<bytes>DTS_DEVELOPER_PUBLIC_KEYS).decode("ascii"))


cdef object _cli_context():
    profile = os.environ.get("DTSHELL_PROFILE")
    arguments = sys.argv[1:]
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item in ("--debug", "-vv", "--verbose", "-q", "--quiet", "--complete"):
            index += 1
        elif item == "--profile":
            if index + 1 >= len(arguments):
                raise _developer_failure("--profile requires a profile name.")
            profile = arguments[index + 1]
            index += 2
        elif item.startswith("--profile="):
            profile = item.split("=", 1)[1]
            index += 1
        elif item == "--":
            index += 1
            break
        else:
            break
    return profile, arguments[index:]


cdef object _database(path):
    import yaml

    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise _developer_failure(f"profile metadata cannot be read: {error}.") from error
    if len(content) > 1024 * 1024:
        raise _developer_failure("profile metadata is too large.")
    try:
        value = yaml.safe_load(content)
    except (yaml.YAMLError, UnicodeError) as error:
        raise _developer_failure("profile metadata is not valid YAML.") from error
    if (
        not isinstance(value, dict) or value.get("version") != 1
        or not isinstance(value.get("data"), dict)
    ):
        raise _developer_failure("profile metadata has an unsupported structure.")
    return value["data"]


cdef object _owned_device():
    root = Path(__file__).resolve().parent
    name = "dt_shell_device"
    expected = root / _native_modules[name]
    module = sys.modules.get(name)
    if module is not None:
        if Path(module.__file__).resolve() != expected:
            raise _failure("computer identity was loaded from outside the verified installation.")
        return module
    spec = importlib.util.spec_from_file_location(name, str(expected))
    if spec is None or spec.loader is None:
        raise _failure("the trusted computer-identity component cannot be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cdef object _identity_context():
    from dt_authentication import DuckietownToken, InvalidToken, ExpiredToken

    issuer = os.environ.get(
        "DTHUB_URL", f"https://{os.environ.get('DTHUB_HOST', 'hub.duckietown.com')}"
    ).rstrip("/")
    if issuer not in _developer_keys():
        raise _developer_failure("this Hub URL is not an approved developer-grant issuer.")
    default_root = Path.home() / ".duckietown" / "shell"
    databases = Path(os.environ.get("DTSHELL_DATABASES", str(default_root / "databases"))).expanduser()
    profile, _ = _cli_context()
    if profile is None:
        profile = _database(databases / "settings.yaml").get("profile")
    if not isinstance(profile, str) or not profile:
        raise _developer_failure("select a profile and set a DT2 identity token before using source overrides.")
    safe_name = re.sub(r"[^\w\d-]", "_", profile)
    profiles = Path(os.environ.get("DTSHELL_PROFILES", str(default_root / "profiles"))).expanduser()
    location = profiles / safe_name / "databases"
    settings = _database(location / "settings.yaml")
    secrets = _database(location / "secrets.yaml")
    distro = settings.get("distro", os.environ.get("DTSHELL_DISTRO"))
    field = "token/dt1" if distro in ("daffy", "daffy-staging") else "token/dt2"
    identity = secrets.get(field)
    if identity is None:
        identity = os.environ.get("DTSHELL_TOKEN") or os.environ.get("DUCKIETOWN_TOKEN")
    if not isinstance(identity, str) or not identity.startswith("dt2-"):
        raise _developer_failure("developer authorization requires a DT2 identity token; use 'dts tok set'.")
    try:
        token = DuckietownToken.from_string(identity, allow_expired=False)
    except (InvalidToken, ExpiredToken, ValueError) as error:
        raise _developer_failure("the active DT2 identity token is invalid or expired; use 'dts tok set'.") from error
    if not token.grants("auth"):
        raise _developer_failure("a plan or scoped authorization token cannot identify your account.")
    device = _owned_device()
    try:
        parameters = device.get_device_parameters()
    except device.DeviceIdentityError as error:
        raise _developer_failure(str(error)) from error
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    cache_key = hashlib.sha256(f"{issuer}:{digest}:{parameters['device_id']}".encode("ascii")).hexdigest()
    return {
        "issuer": issuer, "identity": identity, "identity_sha256": digest, "uid": token.uid,
        "parameters": parameters, "cache": location / "developer" / (cache_key + ".json"),
    }


def _developer_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _developer_failure("the developer grant contains duplicate fields.")
        result[key] = value
    return result


cdef object _validate_developer(token, context, bint allow_expired=False):
    if not isinstance(token, str) or len(token) > 16384:
        raise _developer_failure("the developer grant is missing or too large.")
    try:
        envelope = json.loads(token, object_pairs_hook=_developer_object)
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
            raise _developer_failure("the developer grant has an unsupported envelope.")
        content = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
    except (ValueError, UnicodeError, TypeError, binascii.Error) as error:
        raise _developer_failure("the developer grant has invalid encoding.") from error
    if len(signature) != 64:
        raise _developer_failure("the developer grant signature has an invalid length.")
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(_developer_keys()[context["issuer"]])
        ).verify(signature, content)
    except InvalidSignature as error:
        raise _developer_failure("the developer grant signature is invalid.") from error
    try:
        claims = json.loads(content, object_pairs_hook=_developer_object)
    except (ValueError, UnicodeError) as error:
        raise _developer_failure("the signed developer payload is not valid JSON.") from error
    fields = {
        "format", "audience", "capability", "issuer", "uid", "identity_sha256", "device_id",
        "is_staff", "is_superuser", "issued_at", "expires_at", "renewable",
    }
    if (
        not isinstance(claims, dict) or set(claims) != fields
        or json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") != content
        or type(claims["format"]) is not int or claims["format"] != 1
        or claims["audience"] != "duckietown-shell-developer" or claims["capability"] != "develop:dts"
        or claims["issuer"] != context["issuer"]
        or type(claims["uid"]) is not int or claims["uid"] != context["uid"]
        or claims["identity_sha256"] != context["identity_sha256"]
        or claims["device_id"] != context["parameters"]["device_id"]
        or type(claims["is_staff"]) is not bool or type(claims["is_superuser"]) is not bool
        or not (claims["is_staff"] or claims["is_superuser"])
        or claims["renewable"] is not False
        or type(claims["issued_at"]) is not int or type(claims["expires_at"]) is not int
        or claims["issued_at"] <= 0 or not 0 < claims["expires_at"] - claims["issued_at"] <= 3600
    ):
        raise _developer_failure("the signed grant does not authorize this user, computer, issuer, or capability.")
    now = time.time()
    if claims["issued_at"] > now + 60:
        raise _developer_failure("the developer grant has a future issue time; check this computer's clock.")
    if not allow_expired and now >= claims["expires_at"]:
        raise DeveloperGrantExpired("Developer authorization expired. Restart DTS to reauthorize before loading source code.")
    return claims


cdef object _cached_developer(context, bint allow_expired=False):
    path = context["cache"]
    if path.is_symlink() or path.parent.is_symlink():
        raise _developer_failure("the developer cache contains a symbolic link.")
    try:
        token = path.read_text(encoding="ascii")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as error:
        raise _developer_failure(f"the developer cache cannot be read: {error}.") from error
    return token, _validate_developer(token, context, allow_expired)


cdef object _request_developer(context):
    import requests

    try:
        response = requests.post(
            context["issuer"] + "/api/v1/auth/token/developer/",
            headers={"Authorization": "Token " + context["identity"]},
            json=context["parameters"], timeout=(5, 10), allow_redirects=False,
        )
        if response.is_redirect:
            raise _developer_failure("the Hub redirected the developer request; credentials were not forwarded.")
        response.raise_for_status()
    except requests.RequestException as error:
        raise _developer_failure(
            f"could not authorize with {context['issuer']}: {error}. An unexpired signed grant is required offline."
        ) from error
    if len(response.content) > 65536:
        raise _developer_failure("the Hub developer response is too large.")
    try:
        payload = response.json()
    except ValueError as error:
        raise _developer_failure("the Hub returned invalid JSON for developer authorization.") from error
    if not isinstance(payload, dict) or type(payload.get("success")) is not bool:
        raise _developer_failure("the Hub returned an invalid developer response.")
    if payload["success"] is not True:
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages or not all(isinstance(value, str) for value in messages):
            raise _developer_failure("the Hub rejected developer authorization without a valid explanation.")
        raise _developer_failure(" ".join(messages))
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("token"), str):
        raise _developer_failure("the Hub did not return a signed developer grant.")
    token = result["token"]
    claims = _validate_developer(token, context)
    path = context["cache"]
    if path.is_symlink() or path.parent.is_symlink():
        raise _developer_failure("the developer cache contains a symbolic link.")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".grant-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wt", encoding="ascii") as stream:
                stream.write(token)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    except OSError as error:
        raise _developer_failure(f"the signed developer grant could not be cached: {error}.") from error
    return token, claims


cdef object _overrides():
    result = {}
    for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
        if name not in os.environ:
            continue
        values = os.environ[name].split(os.pathsep) if name == "DTSHELL_PYTHONPATH" else [os.environ[name]]
        if not all(values):
            raise _developer_failure(f"{name} contains an empty override path.")
        paths = tuple(str(Path(value).expanduser().resolve()) for value in values)
        if any(not Path(path).is_dir() for path in paths):
            raise _developer_failure(f"{name} does not identify an existing directory.")
        result[name] = paths
    return result


cdef void _check_developer(bint binding=False) except *:
    if _developer_session is None:
        raise _developer_failure("no authenticated developer session is active.")
    claims = _developer_session["claims"]
    if time.time() >= claims["expires_at"] or time.monotonic() >= _developer_session["deadline"]:
        raise DeveloperGrantExpired("Developer authorization expired. Restart DTS to reauthorize before loading source code.")
    if time.time() < claims["issued_at"] - 60:
        raise _developer_failure("the clock moved behind the developer grant's issue time.")
    if _overrides() != _developer_session["overrides"]:
        raise _developer_failure("source overrides changed during this session; restart DTS to reauthorize them.")
    if binding:
        context = _identity_context()
        if (
            context["issuer"] != claims["issuer"] or context["uid"] != claims["uid"]
            or context["identity_sha256"] != claims["identity_sha256"]
            or context["parameters"]["device_id"] != claims["device_id"]
        ):
            raise _developer_failure("the developer session no longer matches the active identity or this computer.")


class _DeveloperSourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        _check_developer()
        return super().get_code(fullname)


class _DeveloperFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None or _developer_session is None:
            return None
        origin = Path(spec.origin).resolve()
        root = Path(__file__).resolve().parent
        if origin.is_relative_to(root):
            return None
        for paths in _developer_session["overrides"].values():
            if any(origin.is_relative_to(Path(directory)) for directory in paths):
                _check_developer()
                if isinstance(spec.loader, importlib.machinery.SourceFileLoader):
                    spec.loader = _DeveloperSourceLoader(fullname, spec.origin)
                return spec
        return None


cdef void _authorize_overrides(overrides) except *:
    global _developer_session
    if _developer_session is not None:
        _check_developer(True)
        return
    context = _identity_context()
    try:
        cached = _cached_developer(context)
    except DeveloperGrantExpired:
        cached = None
    token, claims = cached if cached is not None else _request_developer(context)
    _developer_session = {
        "claims": claims, "overrides": overrides,
        "deadline": time.monotonic() + max(0, claims["expires_at"] - time.time()),
    }
    for name, paths in overrides.items():
        os.environ[name] = os.pathsep.join(paths)
    sys.meta_path.insert(0, _DeveloperFinder())
    expiration = datetime.datetime.fromtimestamp(claims["expires_at"], datetime.timezone.utc)
    print(
        f"dts : Authenticated developer mode for user {claims['uid']} at {claims['issuer']}; "
        f"source overrides enabled until {expiration.strftime('%d %B %Y at %H:%M:%S UTC')}. "
        "Modified source is not an attested official runtime.",
        file=sys.stderr,
    )


def _failure(detail):
    return ReleaseIntegrityError(
        f"Release integrity check failed: {detail}\n"
        "Reinstall the official package with 'pipx reinstall duckietown-shell'. "
        "Use the source-development workflow in devel.md for local code changes."
    )


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _failure("the manifest contains duplicate fields.")
        result[key] = value
    return result


cdef void _verify(bint management=False) except *:
    global _native_modules
    root = Path(__file__).resolve().parent
    try:
        content = (root / "duckietown_shell.integrity.json").read_bytes()
        signature = (root / "duckietown_shell.integrity.sig").read_bytes()
    except OSError as error:
        raise _failure(f"the signed manifest could not be read: {error}") from error
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex((<bytes>DTS_RELEASE_PUBLIC_KEY).decode("ascii"))
        ).verify(signature, content)
    except InvalidSignature as error:
        raise _failure("the release manifest signature is invalid.") from error
    try:
        manifest = json.loads(content, object_pairs_hook=_object)
    except (ValueError, UnicodeDecodeError) as error:
        raise _failure("the signed manifest is not valid JSON.") from error
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"format", "version", "files", "native_modules"}
        or manifest["format"] != 1
        or not isinstance(manifest["version"], str)
        or not isinstance(manifest["files"], dict)
        or not manifest["files"]
        or not isinstance(manifest["native_modules"], dict)
        or "dt_shell_release" not in manifest["native_modules"]
    ):
        raise _failure("the release manifest has an unsupported structure.")

    files = manifest["files"]
    for relative, digest in files.items():
        if (
            not isinstance(relative, str)
            or "\\" in relative
            or PurePosixPath(relative).is_absolute()
            or any(part in ("", ".", "..") for part in relative.split("/"))
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise _failure("the manifest contains an invalid file entry.")
        path = root.joinpath(*PurePosixPath(relative).parts)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise _failure(f"'{relative}' is a symbolic link or outside the installed package.")
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise _failure(f"'{relative}' could not be read: {error}") from error
        if actual != digest:
            raise _failure(f"'{relative}' has been modified.")

    for package in ("dt_shell", "dt_shell_cli"):
        for path in (root / package).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.relative_to(root).as_posix() not in files:
                raise _failure(f"unexpected file '{path.relative_to(root).as_posix()}'.")

    for name, relative in manifest["native_modules"].items():
        if not isinstance(name, str) or not isinstance(relative, str) or relative not in files:
            raise _failure("the native-module inventory is invalid.")
        source = name.replace(".", "/") + ".py"
        if (root / source).exists():
            raise _failure(f"a Python fallback exists for '{name}'.")

    _native_modules = manifest["native_modules"]
    overrides = {} if management else _overrides()
    if overrides:
        _authorize_overrides(overrides)
    elif _developer_session is not None and not management:
        _check_developer(True)

    for name, module in list(sys.modules.items()):
        if name not in ("dt_shell", "dt_shell_cli", "dt_shell_release", "dt_shell_device") and not name.startswith(
            ("dt_shell.", "dt_shell_cli.")
        ):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None:
            continue
        path = Path(origin).resolve()
        if not path.is_relative_to(root) or path.relative_to(root).as_posix() not in files:
            if (
                _developer_session is not None
                and name not in ("dt_shell_release", "dt_shell_device")
                and any(path.is_relative_to(Path(directory)) for directory
                        in _developer_session["overrides"].get("DTSHELL_LIB", ()))
            ):
                _check_developer()
                continue
            raise _failure(f"'{name}' was loaded from outside the verified installation.")
        if name in manifest["native_modules"] and path != root / manifest["native_modules"][name]:
            raise _failure(f"'{name}' did not load its compiled release component.")


def verify_installation():
    _verify()


def is_developer_mode():
    if _developer_session is None:
        return False
    _check_developer()
    return True


def verify_developer_authorization():
    _check_developer(True)


cdef bint _developer_command(arguments) except *:
    if not arguments or arguments[0] != "developer":
        return False
    _verify(True)
    parser = argparse.ArgumentParser(
        prog="dts [--profile PROFILE] developer",
        description="Manage signed staff/superuser authorization for DTS source overrides.",
    )
    subcommands = parser.add_subparsers(dest="subcommand", title="subcommands")
    for name, description in (
        ("status", "Inspect the local signed developer grant without renewing it."),
        ("renew", "Request a new developer grant after checking current Hub privileges."),
        ("clear", "Remove the cached developer grant for this account and computer."),
    ):
        subcommands.add_parser(name, help=description, description=description)
    parsed = parser.parse_args(arguments[1:])
    if parsed.subcommand is None:
        parser.print_help()
        return True
    context = _identity_context()
    operation = parsed.subcommand
    if operation == "clear":
        try:
            context["cache"].unlink(missing_ok=True)
        except OSError as error:
            raise _developer_failure(f"the developer cache could not be cleared: {error}.") from error
        print("dts : Cached developer grant cleared. Unset source overrides to stop automatic authorization.")
        return True
    grant = _request_developer(context) if operation == "renew" else _cached_developer(context, True)
    if grant is None:
        print("dts : No cached developer grant. Source overrides trigger authorization before loading code.")
        return True
    _, claims = grant
    expiration = datetime.datetime.fromtimestamp(claims["expires_at"], datetime.timezone.utc)
    print(f"dts : Developer account: user {claims['uid']} at {claims['issuer']}")
    print("dts : Computer binding: this computer (no staff/superuser computer limit)")
    state = "valid until" if time.time() < claims["expires_at"] else "expired at"
    print(f"dts : Developer grant: {state} {expiration.strftime('%d %B %Y at %H:%M:%S UTC')}")
    print("dts : New grants require current staff or superuser privileges. Plan eligibility is separate.")
    return True


def manage_developer_authorization(arguments):
    _developer_command(["developer", *arguments])


def verify_command_signature(signature, content):
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex((<bytes>DTS_COMMANDS_PUBLIC_KEY).decode("ascii"))
        ).verify(signature, content)
    except InvalidSignature as error:
        raise ValueError("The command manifest signature is invalid.") from error


def launch():
    try:
        _, arguments = _cli_context()
        if _developer_command(arguments):
            return
        _verify()
        root = str(Path(__file__).resolve().parent)
        if root in sys.path:
            sys.path.remove(root)
        sys.path.insert(0, root)
        from dt_shell_cli.dts import dts
        dts()
    except ReleaseIntegrityError as error:
        print(f"dts : {error}", file=sys.stderr)
        raise SystemExit(78)


def delegated_main():
    try:
        _verify()
        root = str(Path(__file__).resolve().parent)
        # Pin our packages without putting the parent environment's dependencies first.
        for name in ("dt_shell_cli", "dt_shell"):
            if name not in sys.modules:
                paths = list(_developer_session["overrides"].get("DTSHELL_LIB", ())) \
                    if name == "dt_shell" and _developer_session is not None else []
                spec = importlib.machinery.PathFinder.find_spec(name, paths + [root])
                if spec is None or spec.loader is None:
                    raise _failure(f"the verified package '{name}' could not be imported.")
                if paths and isinstance(spec.loader, importlib.machinery.SourceFileLoader):
                    spec.loader = _DeveloperSourceLoader(name, spec.origin)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
        _verify()
        from dt_shell_cli.main import main
        main()
    except ReleaseIntegrityError as error:
        print(f"dts : {error}", file=sys.stderr)
        raise SystemExit(78)
