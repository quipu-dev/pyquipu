import os
from pathlib import Path

# 全局配置中心

# 项目根目录（代码所在位置）
PROJECT_ROOT: Path = Path(__file__).parent.resolve()

# 默认的工作区根目录，可以通过环境变量覆盖
# 在实际运行时，通常由 CLI 参数指定
DEFAULT_WORK_DIR: Path = Path(os.getenv("AI_FS_WORK_DIR", "."))

# 日志级别
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
