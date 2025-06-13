from dt_shell import DTCommandAbs, DTShell
from dt_shell.constants import EMBEDDED_COMMAND_SET_NAME
from typing import List


class DTCommand(DTCommandAbs):
    help = "Shows the list of all the commands available in the shell."

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # show core commands
        print("\nCore commands:")
        keys = sorted(shell.command_set(EMBEDDED_COMMAND_SET_NAME).commands.keys())
        length = len(max(keys, key=len)) + 2
        command_descriptions = shell.profile.command_descriptions
        for cmd in keys:
            print("\t%-*s%s" % (length, cmd, command_descriptions[cmd]["description"] if cmd in command_descriptions else ""))
        # show commands grouped by command sets
        for cs in shell.command_sets:
            if cs.name == EMBEDDED_COMMAND_SET_NAME:
                continue
            print(f"\nCommand set '{cs.name}':")
            keys = sorted(cs.commands.keys())
            length = len(max(keys, key=len)) + 2
            for cmd in keys:
                print("\t%-*s%s" % (length, cmd, command_descriptions[cmd]["description"] if cmd in command_descriptions else ""))

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
