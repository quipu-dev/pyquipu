import logging
import sys
from pathlib import Path

from .config import LOG_LEVEL


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger


def configure_file_logging(log_path: Path):
    root_logger = logging.getLogger()

    # 移除所有现有的 handler (通常是 stderr stream handler)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 确保父目录存在
    if not log_path.parent.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
    file_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)  # TUI 调试模式强制 DEBUG

    logging.info(f"🚀 Logging redirected to file: {log_path}")
