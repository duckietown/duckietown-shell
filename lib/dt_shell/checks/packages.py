from typing import cast, List, Optional

from ..exceptions import UserError
from ..utils import parse_version

__all__ = ["check_package_version", "_get_installed_distributions"]


def _get_installed_distributions(
    local_only: bool = True,
    user_only: bool = False,
    paths: Optional[List[str]] = None,
):
    """Return a list of installed Distribution objects."""
    from pip._internal.metadata import get_environment
    from pip._internal.metadata.pkg_resources import Distribution as _Dist

    env = get_environment(paths)
    dists = env.iter_installed_distributions(
        local_only=local_only,
        user_only=user_only,
        skip=[],
    )
    return [cast(_Dist, dist)._dist for dist in dists]


def check_package_version(PKG: str, min_version: str):
    # pip_version = "?"
    # try:
    #     # noinspection PyCompatibility
    #     from pip import __version__
    #
    #     pip_version = __version__
    #     # noinspection PyCompatibility
    #     from pip._internal.utils.misc import get_installed_distributions
    # except ImportError:
    #     msg = f"""
    #        You need a higher version of "pip".  You have {pip_version}
    #
    #        You can install it with a command like:
    #
    #            pip install -U pip
    #
    #        (Note: your configuration might require a different command.)
    #        """
    #     raise UserError(msg)

    installed = _get_installed_distributions()
    pkgs = {_.project_name: _ for _ in installed}
    if PKG not in pkgs:
        msg = f"""
        You need to have an extra package installed called `{PKG}`.

        You can install it with a command like:

            pip3 install -U "{PKG}>={min_version}"

        (Note: your configuration might require a different command.
         You might need to use "pip" instead of "pip3".)
        """
        raise UserError(msg)

    p = pkgs[PKG]

    installed_version = parse_version(p.version)
    required_version = parse_version(min_version)
    if installed_version < required_version:
        msg = f"""
       You need to have installed {PKG} of at least {min_version}.
       We have detected you have {p.version}.

       Please update {PKG} using pip.

           pip3 install -U  "{PKG}>={min_version}"

       (Note: your configuration might require a different command.
        You might need to use "pip" instead of "pip3".)
       """
        raise UserError(msg)
