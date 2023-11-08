from dt_shell import DTCommandAbs, DTShell


class DTCommand(DTCommandAbs):
    help = "Uninstalls a command set."

    @staticmethod
    def command(shell: DTShell, args):
        # TODO: here we uninstall a command set
        return True

    @staticmethod
    def complete(shell, word, line):
        return []
