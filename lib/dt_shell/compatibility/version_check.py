# used by the following commands files:
#
#   - utils/recipe_utils.py
#
def get_url(*args, **kwargs):
    from dt_shell.checks.version import get_url
    return get_url(*args, **kwargs)
