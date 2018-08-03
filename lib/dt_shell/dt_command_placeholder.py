from .dt_command_abs import DTCommandAbs


class DTCommandPlaceholder(DTCommandAbs):
    fake = True

    @staticmethod
    def command(shell, args):
        return
