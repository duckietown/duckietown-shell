import logging


def install_colored_logs(logger: logging.Logger, level: int = None):
    import coloredlogs
    # NOTE: This is kinda weird, but it seems that the coloredlogs library has
    #       some issues: https://github.com/xolox/python-coloredlogs/issues/18
    # get the current root logger level
    logLevel = logging.getLogger().getEffectiveLevel()
    # install the coloredlogs on our logger and with our level
    coloredlogs.install(level=level or logger.level, logger=logger)
    # restore the root logger level
    logging.getLogger().setLevel(logLevel)
