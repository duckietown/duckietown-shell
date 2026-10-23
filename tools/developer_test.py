"""Test the native developer bootstrap with ephemeral keys, never production signing secrets."""

import argparse
import importlib.machinery
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
from zipfile import ZipFile

from Cython.Build import cythonize
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
from setuptools import Distribution, Extension

from release import (
    ROOT, commands_public_key, renderer_public_keys, renderer_release_public_key,
    viewer_public_keys, viewer_release_public_key,
    seal, verify, read_wheel, wheels,
)


def run(directory: Path):
    supported = set(sys_tags())
    matching = [
        wheel
        for wheel in wheels(directory)
        if parse_wheel_filename(wheel.name)[3] & supported
    ]
    if len(matching) != 1:
        raise ValueError(
            "Expected one signed wheel matching the test interpreter and platform."
        )
    version = str(parse_wheel_filename(matching[0].name)[1])
    verify(matching[0], version)
    data, _, native = read_wheel(matching[0], version)
    command_key = commands_public_key()
    with tempfile.TemporaryDirectory(prefix="dts-developer-native-tests-") as temporary:
        root = Path(temporary)
        developer_private = {
            issuer: Ed25519PrivateKey.generate()
            for issuer in (
                "https://hub.duckietown.com",
                "https://staging-hub.duckietown.com",
            )
        }
        developer_public = {
            issuer: key.public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
            for issuer, key in developer_private.items()
        }
        developer_map = json.dumps(
            developer_public, sort_keys=True, separators=(",", ":")
        )
        key_paths = {}
        for index, (issuer, key) in enumerate(developer_private.items()):
            path = root / f"developer-{index}.pem"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(
                    key.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                )
            key_paths[issuer] = str(path)
        key_file = root / "test-keys.json"
        key_file.write_text(json.dumps(key_paths), encoding="ascii")
        release_key = Ed25519PrivateKey.generate()
        release_public = (
            release_key.public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
        )
        header = root / "dts_release_key.h"
        header.write_text(
            f'static const char DTS_RELEASE_PUBLIC_KEY[] = "{release_public}";\n'
            f'static const char DTS_COMMANDS_PUBLIC_KEY[] = "{command_key}";\n'
            f"static const char DTS_DEVELOPER_PUBLIC_KEYS[] = {json.dumps(developer_map)};\n"
            f'static const char DTM_RELEASE_PUBLIC_KEY[] = "{renderer_release_public_key()}";\n'
            f"static const char DTM_RENDERER_PUBLIC_KEYS[] = {json.dumps(renderer_public_keys())};\n"
            f'static const char DTV_RELEASE_PUBLIC_KEY[] = "{viewer_release_public_key()}";\n'
            f"static const char DTV_AUTH_PUBLIC_KEYS[] = {json.dumps(viewer_public_keys())};\n",
            encoding="ascii",
        )
        source = root / "dt_shell_release.pyx"
        shutil.copyfile(ROOT / "lib/dt_shell_release.pyx", source)
        extensions = cythonize(
            [Extension("dt_shell_release", [str(source)], include_dirs=[str(root)])],
            build_dir=str(root / "cython"),
            compiler_directives={
                "language_level": "3",
                "binding": True,
                "annotation_typing": False,
            },
        )
        distribution = Distribution({"ext_modules": extensions})
        command = distribution.get_command_obj("build_ext")
        command.build_lib = str(root / "extensions")
        command.build_temp = str(root / "compiler")
        command.ensure_finalized()
        command.run()
        binaries = [
            path
            for path in (root / "extensions").iterdir()
            if path.name.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))
        ]
        if len(binaries) != 1:
            raise RuntimeError(
                "Expected one freshly compiled developer test bootstrap."
            )
        data[native["dt_shell_release"]] = binaries[0].read_bytes()
        wheel = root / matching[0].name
        with ZipFile(wheel, "w") as archive:
            for name, content in data.items():
                archive.writestr(name, content)
        environment = {
            "DTS_RELEASE_PUBLIC_KEY": release_public,
            "DTS_COMMANDS_PUBLIC_KEY": command_key,
            "DTS_DEVELOPER_PUBLIC_KEYS": developer_map,
        }
        with patch.dict(os.environ, environment):
            seal(wheel, version, release_key)
            verify(wheel, version)
        installation = root / "runtime"
        with ZipFile(wheel) as archive:
            archive.extractall(installation)
        env = dict(os.environ)
        for name in ("DTSHELL_LIB", "DTSHELL_COMMANDS", "DTSHELL_PYTHONPATH"):
            env.pop(name, None)
        for identity in ("DTS_RELEASE", "DTS_COMMANDS"):
            for suffix in ("_SIGNING_KEY", "_SIGNING_KEY_FILE"):
                env.pop(identity + suffix, None)
        env.update(
            {
                "PYTHONPATH": str(installation),
                "DTS_DEVELOPER_TEST_ROOT": str(installation),
                "DTS_DEVELOPER_TEST_KEYS": str(key_file),
            }
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(ROOT / "lib/dt_shell_tests"),
                "-p",
                "test_developer_runtime.py",
                "-v",
            ],
            env=env,
            check=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        type=Path,
        help="Verified wheelhouse; production files are not modified",
    )
    arguments = parser.parse_args()
    try:
        run(arguments.directory)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Native developer validation failed: {error}\n")


if __name__ == "__main__":
    main()
