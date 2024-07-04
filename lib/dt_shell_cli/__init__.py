import logging
import warnings

from dt_shell_cli.utils import install_colored_logs

warnings.filterwarnings(action='ignore', module='.*paramiko.*')

logging.basicConfig()

# logger dedicated to the shell
logger = logging.getLogger("shell")

# add colored logs
install_colored_logs(logger=logger)
logger.setLevel(logging.INFO)
