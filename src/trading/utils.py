"""Trading logging setup — colored console output for the trading bot."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _color_for_record(record: logging.LogRecord) -> str:
    if not HAS_COLORAMA or not _env_bool("TRADING_COLOR_LOGS", True):
        return ""

    message = record.getMessage()
    if record.levelno >= logging.ERROR:
        return Fore.RED + Style.BRIGHT
    if record.levelno >= logging.WARNING:
        return Fore.YELLOW + Style.BRIGHT
    if "Entered" in message or "Dry run candidate" in message or "Merged " in message or "Redeemed " in message:
        return Fore.GREEN + Style.BRIGHT
    if "Cycle failed" in message or "entry_failed" in message or "partial_orphaned" in message:
        return Fore.RED + Style.BRIGHT
    if "stand_down" in message or "Daily loss limit reached" in message:
        return Fore.YELLOW
    if "Cycle OK" in message:
        return Fore.CYAN
    if "Bot started" in message:
        return Fore.BLUE + Style.BRIGHT
    return Fore.WHITE


class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        color = _color_for_record(record)
        if not color:
            return rendered
        return f"{color}{rendered}{Style.RESET_ALL}"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("polyedge.trading")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    color_fmt = ColorFormatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(color_fmt)
    logger.addHandler(console)

    if os.path.isdir("/app/logs"):
        fh = RotatingFileHandler(
            "/app/logs/trading.log",
            maxBytes=_env_int("TRADING_LOG_MAX_BYTES", 25 * 1024 * 1024),
            backupCount=_env_int("TRADING_LOG_BACKUP_COUNT", 4),
            encoding="utf-8",
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def setup_debug_logging() -> logging.Logger:
    logger = logging.getLogger("polyedge.trading.debug")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    if os.path.isdir("/app/logs"):
        fh = RotatingFileHandler(
            "/app/logs/trading_debug.log",
            maxBytes=_env_int("TRADING_DEBUG_LOG_MAX_BYTES", 40 * 1024 * 1024),
            backupCount=_env_int("TRADING_DEBUG_LOG_BACKUP_COUNT", 3),
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s"))
        logger.addHandler(fh)

    return logger


log = setup_logging()
debug_log = setup_debug_logging()


def strategy_log_tag(strategy_name: str) -> str:
    """Return a short stable tag for a strategy name."""
    if not strategy_name:
        return "UNKNOWN"

    prefix = strategy_name.split("_", 1)[0].strip()
    return prefix or strategy_name
