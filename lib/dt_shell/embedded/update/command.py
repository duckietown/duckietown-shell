from typing import List

from dt_shell import DTCommandAbs


__all__ = ["DTCommand"]

from dt_shell import DTShell


class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        shell.update_commands()
