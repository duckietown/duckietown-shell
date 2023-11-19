import webbrowser
from typing import List

import termcolor
from dt_authentication import InvalidToken, DuckietownToken

from dt_shell import DTCommandAbs, dtslogger

from dt_shell import DTShell


class DTCommand(DTCommandAbs):
    @staticmethod
    def command(shell: DTShell, args: List[str]):
        link = "https://hub.duckietown.com/token"
        example = "dt2-7vEuJsaxeXXXXX-43dzqWFnWd8KBa1yev1g3UKnzVxZkkTbfSJnxzuJjWaANeMf4y6XSXBWTpJ7vWXXXX"
        msg = """
Please enter your Duckietown token.

It looks something like this:

    {example}

To find your token, first login to duckietown.org, and open the page:

    {link}


Enter token: """.format(
            link=href(link), example=dark(example)
        )

        shell.sprint("args: %s" % args.__repr__())

        if args:
            val_in = args[0]
        else:
            webbrowser.open(link, new=2)
            val_in = input(msg)

        s = val_in.strip()
        try:
            token = DuckietownToken.from_string(s)
            if token.uid == -1:
                msg = "This is the sample token. Please use your own token."
                raise ValueError(msg)
            shell.sprint("Correctly identified as uid = %s" % token.uid)
        except InvalidToken as e:
            msg = 'The string "%s" does not look like a valid token:\n%s' % (s, e)
            shell.sprint(msg)
            return False

        # make sure this token is of a version we support
        tokens_supported: List[str] = shell.profile.distro.tokens_supported
        if token.version not in tokens_supported:
            dtslogger.error(f"Token version '{token.version}' not supported by this profile's distro. "
                            f"Only versions supported are {tokens_supported}.")
            return False

        # update the profile token
        shell.profile.secrets.dt_token = s


def dark(x):
    return termcolor.colored(x, attrs=["dark"])


def href(x):
    return termcolor.colored(x, "blue", attrs=["underline"])
