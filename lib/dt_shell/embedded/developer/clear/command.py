from typing import List

from dt_shell import DTCommandAbs, DTShell
from dt_shell.embedded.developer import run_developer_command


class DTCommand(DTCommandAbs):
    @staticmethod
    def command(shell: DTShell, args: List[str]):
        run_developer_command("clear", args, DTCommand.parser)
