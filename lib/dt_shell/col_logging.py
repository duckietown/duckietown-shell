import logging

__all__ = []


def setup_logging_format():
    from logging import Logger, StreamHandler, Formatter
    import logging

    FORMAT = "%(name)15s|%(filename)15s:%(lineno)-4s - %(funcName)-15s| %(message)s"

    logging.basicConfig(format=FORMAT)

    if Logger.root.handlers:  # @UndefinedVariable
        for handler in Logger.root.handlers:  # @UndefinedVariable
            if isinstance(handler, StreamHandler):
                formatter = Formatter(FORMAT)
                handler.setFormatter(formatter)
    else:
        logging.basicConfig(format=FORMAT)


def add_coloring_to_emit_ansi(fn):
    # add methods we need to the class
    def new(*args):
        levelno = args[1].levelno
        if (levelno >= 50):
            color = '\x1b[31m'  # red
        elif (levelno >= 40):
            color = '\x1b[31m'  # red
        elif (levelno >= 30):
            color = '\x1b[33m'  # yellow
        elif (levelno >= 20):
            color = '\x1b[32m'  # green
        elif (levelno >= 10):
            color = '\x1b[35m'  # pink
        else:
            color = '\x1b[0m'  # normal

        args[1].msg = color + str(args[1].msg) + '\x1b[0m'  # normal
        return fn(*args)

    return new


def setup_logging_color():
    import platform

    if platform.system() != 'Windows':
        emit2 = add_coloring_to_emit_ansi(logging.StreamHandler.emit)
        logging.StreamHandler.emit = emit2


def setup_logging():
    # logging.basicConfig()
    setup_logging_color()
    setup_logging_format()
