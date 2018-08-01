from DTCommandAbs import DTCommandAbs

class DTCommandPlaceholder(DTCommandAbs):

    fake = True

    @staticmethod
    def command(shell, line):
        return
