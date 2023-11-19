import typing

DTShell = None

if typing.TYPE_CHECKING:
    # noinspection PyUnresolvedReferences
    import dt_shell

    # noinspection PyUnresolvedReferences
    from dt_shell import DTShell
