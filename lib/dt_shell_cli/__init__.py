import logging
import warnings

warnings.filterwarnings(action='ignore', module='.*paramiko.*')

logging.basicConfig()

# logger dedicated to the shell
logger = logging.getLogger("shell")
logger.setLevel(logging.INFO)
