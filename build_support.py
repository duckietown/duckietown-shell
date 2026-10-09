import os
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension
from setuptools.command.build_py import build_py


PROTECTED_MODULES = (
    "dt_shell.authorization",
    "dt_shell.commands.commands",
    "dt_shell.commands.importer",
    "dt_shell.constants",
    "dt_shell.device",
    "dt_shell.environments",
    "dt_shell.integrity",
    "dt_shell.profile",
    "dt_shell.shell",
    "dt_shell_cli.dts",
    "dt_shell_cli.main",
)
MANIFEST_NAME = "duckietown_shell.integrity.json"
SIGNATURE_NAME = "duckietown_shell.integrity.sig"


def release_public_key() -> str:
    value = os.environ.get("DTS_RELEASE_PUBLIC_KEY", "")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError(
            "DTS_RELEASE_PUBLIC_KEY must contain the 64 lowercase hexadecimal characters of the "
            "Ed25519 release public key. Release builds require a configured signing identity. "
            "For source development, follow devel.md instead of building an unsigned release."
        )
    return value


def native_extensions():
    public_key = release_public_key()
    include = Path("build") / "release-include"
    include.mkdir(parents=True, exist_ok=True)
    header = include / "dts_release_key.h"
    header.write_text(f'static const char DTS_RELEASE_PUBLIC_KEY[] = "{public_key}";\n', encoding="ascii")
    extensions = [Extension(name, ["lib/" + name.replace(".", "/") + ".py"]) for name in PROTECTED_MODULES]
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
        compiler_directives={"language_level": "3", "binding": True, "annotation_typing": False},
    )


class NativeBuildPy(build_py):
    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        return [module for module in modules if f"{module[0]}.{module[1]}" not in PROTECTED_MODULES]

    def run(self):
        super().run()
        # Reused build directories must not retain an earlier Python fallback.
        for name in PROTECTED_MODULES:
            source = Path(self.build_lib) / (name.replace(".", "/") + ".py")
            source.unlink(missing_ok=True)
        for bytecode in Path(self.build_lib).rglob("*.pyc"):
            bytecode.unlink()
