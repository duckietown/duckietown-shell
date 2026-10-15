from importlib.machinery import EXTENSION_SUFFIXES
import sys


def is_release_build() -> bool:
    return __file__.endswith(tuple(EXTENSION_SUFFIXES))


def verify_release_integrity() -> None:
    if is_release_build() or "dt_shell_release" in sys.modules:
        from dt_shell_release import verify_installation

        verify_installation()


def is_developer_mode() -> bool:
    bootstrap = sys.modules.get("dt_shell_release")
    return bootstrap is not None and bootstrap.is_developer_mode()
