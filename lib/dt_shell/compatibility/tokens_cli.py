import datetime
import json
import sys

import dateutil.parser
from future import builtins

from .duckietown_tokens import DuckietownToken


def verify_a_token_main(args=None):
    try:
        if args is None:
            args = sys.argv[1:]

        if args:
            token_s = args[0]
        else:
            msg = "Please enter token:\n> "
            token_s = builtins.input(msg)

        sys.stderr.write("Verifying token %r\n" % token_s)

        try:
            token = DuckietownToken.from_string(token_s)
        except ValueError:
            msg = "Invalid token format."
            sys.stderr.write(msg + "\n")
            sys.exit(3)

        exp_date = dateutil.parser.parse(data["exp"])
        now = datetime.datetime.today()

        if exp_date < now:
            msg = "This token has expired on %s" % exp_date
            sys.stderr.write(msg + "\n")
            sys.exit(6)

        o = dict()
        o["uid"] = data["uid"]
        o["expiration"] = data["exp"]
        msg = json.dumps(o)
        print(msg)
        sys.exit(0)

    except Exception as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(3)
