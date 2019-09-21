from .dt_command_abs import DTCommandAbs

__all__ = ["DTCommandPlaceholder"]


class DTCommandPlaceholder(DTCommandAbs):
    fake = True

    @staticmethod
    def command(shell, args):
        return
