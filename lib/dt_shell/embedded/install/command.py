from dt_shell import DTCommandAbs, DTShell


class DTCommand(DTCommandAbs):
    help = "Installs a new command set."

    @staticmethod
    def command(shell: DTShell, args):
        # TODO: here we install a new command set
        return True

    @staticmethod
    def complete(shell, word, line):
        return []
