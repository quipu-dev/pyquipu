import logging
import sys
from .config import LOG_LEVEL

def setup_logging():
    """配置全局日志记录器"""
    root_logger = logging.getLogger("neuron_ops")
    root_logger.setLevel(LOG_LEVEL)
    
    # 避免重复添加 handler
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger
