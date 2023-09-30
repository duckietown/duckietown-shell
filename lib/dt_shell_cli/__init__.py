import logging


logging.basicConfig()

# logger dedicated to the shell
logger = logging.getLogger("shell")
logger.setLevel(logging.INFO)
