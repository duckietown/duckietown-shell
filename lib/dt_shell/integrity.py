import cython


def is_release_build() -> bool:
    return cython.compiled


def verify_release_integrity() -> None:
    if cython.compiled:
        from dt_shell_release import verify_installation

        verify_installation()
