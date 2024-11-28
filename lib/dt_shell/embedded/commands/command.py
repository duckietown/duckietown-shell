from typing import List

from dt_shell.constants import EMBEDDED_COMMAND_SET_NAME

from dt_shell import DTCommandAbs, DTShell


class DTCommand(DTCommandAbs):
    help = "Shows the list of all the commands available in the shell."

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # show core commands
        print("\nCore commands:")
        for cmd in shell.command_set(EMBEDDED_COMMAND_SET_NAME).commands.keys():
            print("\t%s" % cmd)

        # show commands grouped by command sets
        for cs in shell.command_sets:
            if cs.name == EMBEDDED_COMMAND_SET_NAME:
                continue
            print(f"\nCommand set '{cs.name}':")
            for cmd in cs.commands.keys():
                print("\t%s" % cmd)

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
