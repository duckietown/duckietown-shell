"""Build-side signing and validation. Private keys never enter a wheel."""

import argparse
import ast
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
from zipfile import BadZipFile, ZipFile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from packaging.tags import sys_tags
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_support import MANIFEST_NAME, PROTECTED_MODULES, SIGNATURE_NAME, release_public_key

PYTHONS = {"cp310", "cp311", "cp312"}
PLATFORMS = {"linux-x86_64", "linux-aarch64", "macos-x86_64", "macos-arm64", "windows-amd64"}


def current_version() -> str:
    tree = ast.parse((ROOT / "lib/dt_shell/__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            return str(ast.literal_eval(node.value))
    raise ValueError("No shell version found.")


def platform_group(platform: str, portable: bool) -> str:
    if platform.startswith("manylinux") or (not portable and platform.startswith("linux_")):
        for arch in ("x86_64", "aarch64"):
            if platform.endswith("_" + arch):
                return "linux-" + arch
    if platform.startswith("macosx_"):
        for arch in ("x86_64", "arm64"):
            if platform.endswith("_" + arch):
                return "macos-" + arch
    if platform == "win_amd64":
        return "windows-amd64"
    raise ValueError(f"Unsupported wheel platform: {platform}.")


def wheel_coordinates(path: Path, version: str, portable: bool = False) -> set[tuple[str, str]]:
    name, found_version, _, tags = parse_wheel_filename(path.name)
    if canonicalize_name(name) != "duckietown-shell" or found_version != Version(version):
        raise ValueError(
            f"Unexpected package or version in '{path.name}'; expected duckietown-shell {version}."
        )
    coordinates = set()
    for tag in tags:
        if tag.interpreter not in PYTHONS or tag.abi != tag.interpreter:
            raise ValueError(f"'{path.name}' is not a supported CPython native wheel.")
        coordinates.add((tag.interpreter, platform_group(tag.platform, portable)))
    if len(coordinates) != 1:
        raise ValueError(f"'{path.name}' mixes different interpreter or platform targets.")
    return coordinates


def read_wheel(path: Path, version: str) -> tuple[dict[str, bytes], str, dict[str, str]]:
    wheel_coordinates(path, version)
    with ZipFile(path) as archive:
        infos = archive.infolist()
        if len({info.filename for info in infos}) != len(infos):
            raise ValueError(f"Duplicate archive entries in '{path.name}'.")
        data = {}
        for info in infos:
            name = info.filename
            parts = name.rstrip("/").split("/")
            if (
                "\\" in name
                or PurePosixPath(name).is_absolute()
                or any(part in ("", ".", "..") for part in parts)
                or stat.S_ISLNK(info.external_attr >> 16)
            ):
                raise ValueError(f"Unsafe wheel entry in '{path.name}'.")
            if not info.is_dir():
                data[name] = archive.read(info)

    metadata_paths = [name for name in data if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        raise ValueError(f"'{path.name}' must contain exactly one package metadata directory.")
    metadata_path = metadata_paths[0]
    dist_info = metadata_path.rsplit("/", 1)[0]
    metadata = BytesParser().parsebytes(data[metadata_path])
    if (
        canonicalize_name(metadata.get("Name", "")) != "duckietown-shell"
        or metadata.get("Version") != version
        or SpecifierSet(metadata.get("Requires-Python", "")) != SpecifierSet(">=3.10,<3.13")
    ):
        raise ValueError(f"Incorrect package/version/Python metadata in '{path.name}'.")
    wheel_metadata = BytesParser().parsebytes(data.get(dist_info + "/WHEEL", b""))
    if wheel_metadata.get("Root-Is-Purelib") != "false":
        raise ValueError(f"'{path.name}' must not be a pure-Python wheel.")
    entry_points = data.get(dist_info + "/entry_points.txt", b"").decode("utf-8")
    if "dts = dt_shell_release:launch" not in entry_points:
        raise ValueError(f"'{path.name}' does not use the protected launcher.")

    native_modules = {}
    if any(name.endswith((".pyc", ".pyx", ".pxd", ".c", ".h")) for name in data):
        raise ValueError(f"'{path.name}' contains bytecode or native build sources.")
    for module in (*PROTECTED_MODULES, "dt_shell_release"):
        stem = module.replace(".", "/")
        for suffix in (".py", ".pyc", ".pyx", ".pxd", ".c", ".h"):
            if stem + suffix in data:
                raise ValueError(f"Python or generated-source fallback for '{module}' in '{path.name}'.")
        matches = [
            name
            for name in data
            if name.startswith(stem + ".") and "/" not in name[len(stem) :] and name.endswith((".so", ".pyd"))
        ]
        if len(matches) != 1:
            raise ValueError(f"'{path.name}' must contain one native component for '{module}'.")
        native_modules[module] = matches[0]
    public_key = release_public_key()
    if public_key.encode("ascii") not in data[native_modules["dt_shell_release"]]:
        raise ValueError(f"'{path.name}' was not built with DTS_RELEASE_PUBLIC_KEY.")
    for required in (
        "dt_shell/__init__.py",
        "dt_shell_cli/__init__.py",
        "dt_shell/assets/requirements.txt",
        "dt_shell/embedded/command_descriptions.yaml",
    ):
        if required not in data:
            raise ValueError(f"Missing '{required}' in '{path.name}'.")
    return data, dist_info + "/RECORD", native_modules


def manifest_bytes(
    data: dict[str, bytes], record: str, native_modules: dict[str, str], version: str
) -> bytes:
    files = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in data.items()
        if name not in (MANIFEST_NAME, SIGNATURE_NAME, record)
    }
    manifest = {"format": 1, "version": version, "files": files, "native_modules": native_modules}
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def signing_key() -> Ed25519PrivateKey:
    key_file = os.environ.get("DTS_RELEASE_SIGNING_KEY_FILE")
    key_pem = os.environ.get("DTS_RELEASE_SIGNING_KEY")
    if bool(key_file) == bool(key_pem):
        raise ValueError("Set exactly one of DTS_RELEASE_SIGNING_KEY_FILE or DTS_RELEASE_SIGNING_KEY.")
    if key_file:
        content = Path(key_file).read_bytes()
    elif key_pem:
        content = key_pem.encode("ascii")
    else:
        raise ValueError("No release signing key configured.")
    try:
        key = serialization.load_pem_private_key(content, password=None)
    except (ValueError, TypeError) as error:
        raise ValueError(
            "The release signing secret must be an unencrypted Ed25519 private key in PEM format."
        ) from error
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The release signing secret is not an Ed25519 key.")
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if public.hex() != release_public_key():
        raise ValueError("The signing key does not match DTS_RELEASE_PUBLIC_KEY.")
    return key


def seal(path: Path, version: str, key: Ed25519PrivateKey) -> None:
    data, record, native_modules = read_wheel(path, version)
    data[MANIFEST_NAME] = manifest_bytes(data, record, native_modules, version)
    data[SIGNATURE_NAME] = key.sign(data[MANIFEST_NAME])
    rows = io.StringIO(newline="")
    writer = csv.writer(rows, lineterminator="\n")
    for name, content in sorted(data.items()):
        if name != record:
            digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
            writer.writerow((name, "sha256=" + digest, str(len(content))))
    writer.writerow((record, "", ""))
    data[record] = rows.getvalue().encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    try:
        with ZipFile(path) as original, ZipFile(temporary, "w") as output:
            existing = {info.filename: info for info in original.infolist() if not info.is_dir()}
            for name, content in data.items():
                output.writestr(existing.get(name, name), content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    verify(path, version)
    print(f"Signed {path.name}")


def verify(path: Path, version: str) -> None:
    data, record, native_modules = read_wheel(path, version)
    if MANIFEST_NAME not in data or SIGNATURE_NAME not in data:
        raise ValueError(f"'{path.name}' is unsigned.")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(release_public_key()))
    try:
        key.verify(data[SIGNATURE_NAME], data[MANIFEST_NAME])
    except InvalidSignature as error:
        raise ValueError(f"Invalid release signature in '{path.name}'.") from error
    if data[MANIFEST_NAME] != manifest_bytes(data, record, native_modules, version):
        raise ValueError(f"'{path.name}' does not match its signed manifest.")
    rows = list(csv.reader(io.StringIO(data.get(record, b"").decode("utf-8"))))
    if len(rows) != len(data) or any(len(row) != 3 for row in rows):
        raise ValueError(f"Invalid wheel RECORD in '{path.name}'.")
    entries = {row[0]: row[1:] for row in rows}
    if len(entries) != len(rows) or set(entries) != set(data):
        raise ValueError(f"Wheel RECORD inventory mismatch in '{path.name}'.")
    for name, content in data.items():
        expected = ["", ""]
        if name != record:
            digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
            expected = ["sha256=" + digest, str(len(content))]
        if entries[name] != expected:
            raise ValueError(f"Incorrect wheel RECORD entry for '{name}' in '{path.name}'.")


def wheels(directory: Path) -> list[Path]:
    paths = sorted(directory.iterdir())
    if not paths or any(not path.is_file() or path.suffix != ".whl" for path in paths):
        raise ValueError(
            f"'{directory}' must contain only release wheels, with no source archives or stale files."
        )
    return paths


def verify_directory(directory: Path, version: str, require_matrix: bool) -> list[Path]:
    paths = wheels(directory)
    coordinates = set()
    for path in paths:
        current = wheel_coordinates(path, version, portable=require_matrix)
        if current & coordinates:
            raise ValueError(f"Duplicate release target in '{path.name}'.")
        coordinates.update(current)
        verify(path, version)
    expected = {(python, platform) for python in PYTHONS for platform in PLATFORMS}
    if require_matrix and coordinates != expected:
        raise ValueError(f"Incomplete release matrix; missing targets: {sorted(expected - coordinates)}.")
    print(f"Verified {len(paths)} signed native wheel(s) for {version}.")
    return paths


def keygen(private: Path, public: Path) -> None:
    if private.resolve() == public.resolve():
        raise ValueError("Private and public key paths must differ.")
    for path in (private, public):
        if path.resolve().is_relative_to(ROOT) or path.exists():
            raise ValueError("Key paths must be new files outside the repository.")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    descriptor = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(pem)
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    with public.open("x", encoding="ascii") as stream:
        stream.write(raw.hex() + "\n")
    print(f"Created private key at {private} and public key at {public}. Keep the private key in CI secrets.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("keygen")
    generate.add_argument("--private-key", type=Path, required=True)
    generate.add_argument("--public-key", type=Path, required=True)
    for name in ("seal", "verify", "publish", "install"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        command.add_argument("--version", default=current_version())
        if name == "verify":
            command.add_argument("--require-matrix", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "keygen":
            keygen(arguments.private_key, arguments.public_key)
        elif arguments.command == "seal":
            key = signing_key()
            for path in wheels(arguments.directory):
                seal(path, arguments.version, key)
        else:
            paths = verify_directory(
                arguments.directory,
                arguments.version,
                arguments.command == "publish" or getattr(arguments, "require_matrix", False),
            )
            if arguments.command == "publish":
                subprocess.run([sys.executable, "-m", "twine", "check", *map(str, paths)], check=True)
                subprocess.run(
                    [sys.executable, "-m", "twine", "upload", "--non-interactive", *map(str, paths)],
                    check=True,
                )
            elif arguments.command == "install":
                supported = set(sys_tags())
                matches = [path for path in paths if parse_wheel_filename(path.name)[3] & supported]
                if len(matches) != 1:
                    raise ValueError("Expected exactly one signed wheel matching this Python and platform.")
                subprocess.run([sys.executable, "-m", "pip", "install", str(matches[0])], check=True)
                subprocess.run(
                    [sys.executable, "-c", "import dt_shell_release; dt_shell_release.verify_installation()"],
                    check=True,
                )
    except (ValueError, RuntimeError, OSError, BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release operation failed: {error}\n")


if __name__ == "__main__":
    main()
