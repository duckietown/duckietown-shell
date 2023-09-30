import os.path

SHELL_CLI_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.expanduser("~/.duckietown/shell/")

# read requirements list embedded as asset into the release
SHELL_REQUIREMENTS_LIST: str = os.path.join(os.path.dirname(__file__), "assets", "requirements.txt")
assert os.path.exists(SHELL_REQUIREMENTS_LIST)
