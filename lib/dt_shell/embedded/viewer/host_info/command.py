from dt_shell import DTCommandAbs
from dt_shell.viewer import host_info
from dt_shell.viewer_runtime import canonical


class DTCommand(DTCommandAbs):
    help = "Report native Viewer host identity and trust without enrolling another computer"

    @staticmethod
    def command(shell, args, **kwargs):
        print("DTS_VIEWER_HOST_INFO=" + canonical(host_info()).decode("ascii"))
