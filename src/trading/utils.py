"""Trading logging setup — colored console output for the trading bot."""

import logging
import os
import sys

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("polyedge.trading")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fmt = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if os.path.isdir("/app/logs"):
        fh = logging.FileHandler("/app/logs/trading.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def setup_debug_logging() -> logging.Logger:
    logger = logging.getLogger("polyedge.trading.debug")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if os.path.isdir("/app/logs"):
        fh = logging.FileHandler("/app/logs/trading_debug.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s"))
        logger.addHandler(fh)

    return logger


log = setup_logging()
debug_log = setup_debug_logging()
