from typing import List

from dt_shell import DTCommandAbs, DTShell


class DTCommand(DTCommandAbs):
    help = "Uninstalls a command set."

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # TODO: here we uninstall a command set
        return True

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
