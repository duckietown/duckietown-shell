from dt_shell import DTCommandAbs, DTShell


class DTCommand(DTCommandAbs):
    help = "Shows the list of all the commands available in the shell."

    @staticmethod
    def command(shell: DTShell, args):
        # show core commands
        print("\nCore commands:")
        for cmd in shell.command_set("embedded").commands.keys():
            print("\t%s" % cmd)

        # show commands grouped by command sets
        for cs in shell.command_sets:
            if cs.name == "embedded":
                continue
            print(f"\nCommand set '{cs.name}':")
            for cmd in cs.commands.keys():
                print("\t%s" % cmd)

    @staticmethod
    def complete(shell, word, line):
        return []
