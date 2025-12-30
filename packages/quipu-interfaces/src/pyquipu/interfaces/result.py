from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class QuipuResult:
    success: bool
    exit_code: int
    message: str = ""  # Will hold the message ID for the bus
    data: Any = None
    error: Optional[Exception] = None
    msg_kwargs: Dict[str, Any] = field(default_factory=dict)
