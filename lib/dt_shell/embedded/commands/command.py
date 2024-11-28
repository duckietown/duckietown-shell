import os, yaml
from dt_shell import DTCommandAbs, DTShell
from dt_shell.constants import EMBEDDED_COMMAND_SET_NAME
from typing import List

with open(f"{os.path.dirname(__file__)}/command_descriptions.yaml") as stream:
    command_descriptions = yaml.safe_load(stream)


class DTCommand(DTCommandAbs):
    help = "Shows the list of all the commands available in the shell."

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # show core commands
        print("\nCore commands:")
        for cmd in shell.command_set(EMBEDDED_COMMAND_SET_NAME).commands.keys():
            print("\t%-*s%s" % (15, cmd, command_descriptions[cmd]["description"]))
        # show commands grouped by command sets
        for cs in shell.command_sets:
            if cs.name == EMBEDDED_COMMAND_SET_NAME:
                continue
            print(f"\nCommand set '{cs.name}':")
            for cmd in cs.commands.keys():
                print("\t%-*s%s" % (15, cmd, command_descriptions[cmd]["description"]))

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
