# used by the following commands files:
#
#   - commands/command.py
#   - install/command.py
#
def _get_commands(*args, **kwargs):
    from dt_shell.commands import get_commands
    return get_commands(*args, **kwargs)

