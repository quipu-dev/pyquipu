from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class QuipuResult:
    """
    Quipu 业务逻辑执行结果的标准容器。
    用于在 Controller 和 Shell 之间传递状态，避免直接抛出 SystemExit。
    """

    success: bool
    exit_code: int
    message: str = ""
    data: Any = None
    error: Optional[Exception] = None
