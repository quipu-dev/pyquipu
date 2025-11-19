from typing import TypedDict, List

class Statement(TypedDict):
    """表示解析后的单个操作语句"""
    act: str
    contexts: List[str]
