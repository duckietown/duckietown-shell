# used by the following commands files:
#
#   - commands/command.py
#   - install/command.py
#
from typing import Optional, Dict


def _get_commands(*args, **kwargs) -> Optional[Dict[str, object]]:
    import dt_shell
    return dt_shell.shell.commands
