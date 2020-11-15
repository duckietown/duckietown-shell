import logging

__all__ = []


def setup_logging_format():
    from logging import Logger, StreamHandler, Formatter
    import logging

    FORMAT = "%(name)15s|ds|%(filename)15s:%(lineno)-4s - %(funcName)-15s| %(message)s"

    logging.basicConfig(format=FORMAT)

    # noinspection PyUnresolvedReferences
    root = Logger.root
    if root.handlers:
        for handler in root.handlers:
            if isinstance(handler, StreamHandler):
                formatter = Formatter(FORMAT)
                handler.setFormatter(formatter)
    else:
        logging.basicConfig(format=FORMAT)


def add_coloring_to_emit_ansi(fn):
    # add methods we need to the class
    def new(*args):
        levelno = args[1].levelno
        if levelno >= 50:
            color = "\x1b[31m"  # red
        elif levelno >= 40:
            color = "\x1b[31m"  # red
        elif levelno >= 30:
            color = "\x1b[33m"  # yellow
        elif levelno >= 20:
            color = "\x1b[32m"  # green
        elif levelno >= 10:
            color = "\x1b[35m"  # pink
        else:
            color = "\x1b[0m"  # normal

        msg = str(args[1].msg)

        lines = msg.split("\n")

        def color_line(l):
            return "%s%s%s" % (color, l, "\x1b[0m")  # normal

        lines = list(map(color_line, lines))

        args[1].msg = "\n".join(lines)
        return fn(*args)

    return new


def setup_logging_color():
    import platform

    if platform.system() != "Windows":
        emit2 = add_coloring_to_emit_ansi(logging.StreamHandler.emit)
        logging.StreamHandler.emit = emit2


def setup_logging():
    # logging.basicConfig()
    setup_logging_color()
    setup_logging_format()
