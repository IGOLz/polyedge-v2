"""Shared logging setup — consistent across all services.

Usage:
    from shared.logging import setup_logger
    logger = setup_logger("core")   # or "analysis", "trading"
"""

import logging
import os
import sys


def setup_logger(
    service_name: str,
    level: int = logging.INFO,
    log_dir: str = "/app/logs",
) -> logging.Logger:
    """Create and return a logger for a service.

    Console output always enabled; file output enabled only if log_dir exists.
    """
    logger = logging.getLogger(f"polyedge.{service_name}")
    logger.setLevel(level)

    if logger.handlers:
        return logger  # already configured

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Console
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File (optional)
    if os.path.isdir(log_dir):
        fh = logging.FileHandler(
            os.path.join(log_dir, f"{service_name}.log"),
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ("httpcore", "httpx", "websockets.client", "websockets.connection"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logger
