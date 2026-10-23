import os
import json
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension
from setuptools.command.build_py import build_py


PROTECTED_MODULES = (
    "dt_shell.authorization",
    "dt_shell.commands.artifacts",
    "dt_shell.commands.commands",
    "dt_shell.commands.importer",
    "dt_shell.constants",
    "dt_shell.device",
    "dt_shell.engine",
    "dt_shell.engine_runtime",
    "dt_shell.environments",
    "dt_shell.integrity",
    "dt_shell.profile",
    "dt_shell.renderer",
    "dt_shell.viewer",
    "dt_shell.viewer_runtime",
    "dt_shell.shell",
    "dt_shell_cli.dts",
    "dt_shell_cli.main",
    "dt_shell_device",
)
MANIFEST_NAME = "duckietown_shell.integrity.json"
SIGNATURE_NAME = "duckietown_shell.integrity.sig"


def _public_key(variable: str) -> str:
    value = os.environ.get(variable, "")
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RuntimeError(
            f"{variable} must contain the 64 lowercase hexadecimal characters of the "
            "Ed25519 public key. Release builds require configured signing identities. "
            "For source development, follow devel.md instead of building an unsigned release."
        )
    return value


def release_public_key() -> str:
    return _public_key("DTS_RELEASE_PUBLIC_KEY")


def commands_public_key() -> str:
    return _public_key("DTS_COMMANDS_PUBLIC_KEY")


def _hub_public_keys(variable: str, excluded: tuple[str, ...]) -> str:
    try:
        keys = json.loads(os.environ.get(variable, ""))
    except ValueError as error:
        raise RuntimeError(
            f"{variable} must be a JSON mapping of approved Hub URLs to Ed25519 public keys."
        ) from error
    approved = {"https://hub.duckietown.com", "https://staging-hub.duckietown.com"}
    if (
        not isinstance(keys, dict)
        or set(keys) != approved
        or any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in keys.values()
        )
        or len(set(keys.values())) != len(approved)
        or any(
            value in excluded
            for value in keys.values()
        )
    ):
        raise RuntimeError(
            f"{variable} must pin separate 64-character lowercase Ed25519 public keys "
            "for https://hub.duckietown.com and https://staging-hub.duckietown.com, distinct from other trust keys."
        )
    return json.dumps(keys, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def developer_public_keys() -> str:
    return _hub_public_keys(
        "DTS_DEVELOPER_PUBLIC_KEYS", (release_public_key(), commands_public_key())
    )


def renderer_release_public_key() -> str:
    value = _public_key("DTM_RELEASE_PUBLIC_KEY")
    if value in (
        release_public_key(), commands_public_key(),
        *json.loads(developer_public_keys()).values(),
    ):
        raise RuntimeError("DTM_RELEASE_PUBLIC_KEY must be distinct from DTS trust keys.")
    return value


def renderer_public_keys() -> str:
    return _hub_public_keys(
        "DTM_RENDERER_PUBLIC_KEYS",
        (
            release_public_key(), commands_public_key(), renderer_release_public_key(),
            *json.loads(developer_public_keys()).values(),
        ),
    )


def viewer_release_public_key() -> str:
    value = _public_key("DTV_RELEASE_PUBLIC_KEY")
    excluded = (
        release_public_key(), commands_public_key(), renderer_release_public_key(),
        *json.loads(developer_public_keys()).values(), *json.loads(renderer_public_keys()).values(),
    )
    if value in excluded:
        raise RuntimeError("DTV_RELEASE_PUBLIC_KEY must be distinct from other DTS and renderer keys.")
    return value


def viewer_public_keys() -> str:
    return _hub_public_keys(
        "DTV_AUTH_PUBLIC_KEYS",
        (
            release_public_key(), commands_public_key(), renderer_release_public_key(),
            viewer_release_public_key(), *json.loads(developer_public_keys()).values(),
            *json.loads(renderer_public_keys()).values(),
        ),
    )

def engine_release_public_key() -> str:
    value = _public_key("DTM_ENGINE_RELEASE_PUBLIC_KEY")
    excluded = (
        release_public_key(), commands_public_key(), renderer_release_public_key(),
        viewer_release_public_key(), *json.loads(developer_public_keys()).values(),
        *json.loads(renderer_public_keys()).values(), *json.loads(viewer_public_keys()).values(),
    )
    if value in excluded:
        raise RuntimeError("DTM_ENGINE_RELEASE_PUBLIC_KEY must be distinct from other trust keys.")
    return value


def engine_public_keys() -> str:
    return _hub_public_keys(
        "DTM_ENGINE_PUBLIC_KEYS",
        (
            release_public_key(), commands_public_key(), renderer_release_public_key(),
            viewer_release_public_key(), engine_release_public_key(),
            *json.loads(developer_public_keys()).values(),
            *json.loads(renderer_public_keys()).values(), *json.loads(viewer_public_keys()).values(),
        ),
    )


def native_extensions():
    public_key = release_public_key()
    command_key = commands_public_key()
    developer_keys = developer_public_keys()
    renderer_release_key = renderer_release_public_key()
    renderer_keys = renderer_public_keys()
    viewer_release_key = viewer_release_public_key()
    viewer_keys = viewer_public_keys()
    engine_release_key = engine_release_public_key()
    engine_keys = engine_public_keys()
    if public_key == command_key:
        raise RuntimeError(
            "DTS_RELEASE_PUBLIC_KEY and DTS_COMMANDS_PUBLIC_KEY must identify different keys."
        )
    include = Path("build") / "release-include"
    include.mkdir(parents=True, exist_ok=True)
    header = include / "dts_release_key.h"
    header.write_text(
        f'static const char DTS_RELEASE_PUBLIC_KEY[] = "{public_key}";\n'
        f'static const char DTS_COMMANDS_PUBLIC_KEY[] = "{command_key}";\n'
        f"static const char DTS_DEVELOPER_PUBLIC_KEYS[] = {json.dumps(developer_keys)};\n",
        encoding="ascii",
    )
    with header.open("a", encoding="ascii") as stream:
        stream.write(
            f'static const char DTM_RELEASE_PUBLIC_KEY[] = "{renderer_release_key}";\n'
            f"static const char DTM_RENDERER_PUBLIC_KEYS[] = {json.dumps(renderer_keys)};\n"
            f'static const char DTV_RELEASE_PUBLIC_KEY[] = "{viewer_release_key}";\n'
            f"static const char DTV_AUTH_PUBLIC_KEYS[] = {json.dumps(viewer_keys)};\n"
            f'static const char DTM_ENGINE_RELEASE_PUBLIC_KEY[] = "{engine_release_key}";\n'
            f"static const char DTM_ENGINE_PUBLIC_KEYS[] = {json.dumps(engine_keys)};\n"
        )
    extensions = [
        Extension(name, ["lib/" + name.replace(".", "/") + ".py"])
        for name in PROTECTED_MODULES
    ]
    extensions.append(
        Extension(
            "dt_shell_release",
            ["lib/dt_shell_release.pyx"],
            include_dirs=[str(include.resolve())],
            depends=[str(header.resolve())],
        )
    )
    return cythonize(
        extensions,
        build_dir="build/cython",
        compiler_directives={
            "language_level": "3",
            "binding": True,
            "annotation_typing": False,
        },
    )


class NativeBuildPy(build_py):
    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        return [
            module
            for module in modules
            if f"{module[0]}.{module[1]}" not in PROTECTED_MODULES
        ]

    def run(self):
        super().run()
        # Reused build directories must not retain an earlier Python fallback.
        for name in PROTECTED_MODULES:
            source = Path(self.build_lib) / (name.replace(".", "/") + ".py")
            source.unlink(missing_ok=True)
        for bytecode in Path(self.build_lib).rglob("*.pyc"):
            bytecode.unlink()
