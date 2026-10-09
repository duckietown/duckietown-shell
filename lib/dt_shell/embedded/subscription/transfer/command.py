from typing import List

from dt_shell import DTCommandAbs, DTShell, UserError
from dt_shell.authorization import transfer_ente_device


class DTCommand(DTCommandAbs):
    @staticmethod
    def command(shell: DTShell, args: List[str]):
        if args:
            raise UserError("Usage: dts subscription transfer")
        shell.sprint(transfer_ente_device(shell))
