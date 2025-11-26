import logging
import sys
from .config import LOG_LEVEL


def setup_logging():
    """配置全局日志记录器"""
    # 配置根记录器，确保所有模块(acts.*, core.*)的日志都能被捕获
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    # 避免重复添加 handler
    if not root_logger.handlers:
        # 关键修改: 将日志输出到 stderr，防止污染管道 stdout
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger
