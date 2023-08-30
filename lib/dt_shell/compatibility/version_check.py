# used by the following commands files:
#
#   - utils/recipe_utils.py
#
def get_url(*args, **kwargs):
    from ..checks.version import get_url
    return get_url(*args, **kwargs)
