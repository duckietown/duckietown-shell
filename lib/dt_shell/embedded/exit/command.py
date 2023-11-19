from typing import List

from dt_shell import DTCommandAbs, DTShell


class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        print("Bye bye!")
        exit()
