import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

cdef extern from "dts_release_key.h":
    const char DTS_RELEASE_PUBLIC_KEY[]


class ReleaseIntegrityError(RuntimeError):
    pass


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


cdef void _verify() except *:
    for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
        if name in os.environ:
            raise _failure(f"{name} source overrides are not supported by the compiled release.")

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

    for name, module in list(sys.modules.items()):
        if name not in ("dt_shell", "dt_shell_cli", "dt_shell_release") and not name.startswith(
            ("dt_shell.", "dt_shell_cli.")
        ):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None:
            continue
        path = Path(origin).resolve()
        if not path.is_relative_to(root) or path.relative_to(root).as_posix() not in files:
            raise _failure(f"'{name}' was loaded from outside the verified installation.")
        if name in manifest["native_modules"] and path != root / manifest["native_modules"][name]:
            raise _failure(f"'{name}' did not load its compiled release component.")


def verify_installation():
    _verify()


def launch():
    try:
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
                spec = importlib.machinery.PathFinder.find_spec(name, [root])
                if spec is None or spec.loader is None:
                    raise _failure(f"the verified package '{name}' could not be imported.")
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
        _verify()
        from dt_shell_cli.main import main
        main()
    except ReleaseIntegrityError as error:
        print(f"dts : {error}", file=sys.stderr)
        raise SystemExit(78)
