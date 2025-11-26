from __future__ import annotations
import dataclasses
from pathlib import Path
from typing import Optional, List, Dict  # <-- 引入 List
from datetime import datetime


@dataclasses.dataclass
class QuipuNode:
    """
    表示 Axon 历史图谱中的一个节点。

    这个数据类封装了从文件名和文件内容中解析出的所有元数据和状态信息。
    """

    # 从文件名解析
    input_tree: str
    output_tree: str
    timestamp: datetime

    # 从文件物理路径
    filename: Path

    # 从 Frontmatter 解析
    node_type: str  # "plan" | "capture"
    parent_hint: Optional[str] = None

    # 文件主体内容
    content: str = ""

    # 从元数据或内容生成的单行摘要
    summary: str = ""

    # --- 图遍历字段 (由加载器填充) ---
    parent: Optional[QuipuNode] = None
    children: List[QuipuNode] = dataclasses.field(default_factory=list)

    @property
    def short_hash(self) -> str:
        """返回一个用于UI展示的简短哈希"""
        return self.output_tree[:7]

    @property
    def siblings(self) -> List[QuipuNode]:
        """获取所有兄弟节点 (包括自身)，按时间排序"""
        if not self.parent:
            return [self]
        return self.parent.children
