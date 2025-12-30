from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path
from typing import List, Optional  # <-- 引入 List


@dataclasses.dataclass
class QuipuNode:
    # 核心标识符
    commit_hash: str  # Git Commit 哈希，代表历史图谱中的一个事件
    output_tree: str  # Git Tree 哈希，代表此次事件产生的文件系统状态快照
    input_tree: str  # Git Tree 哈希，代表此次事件的输入状态
    timestamp: datetime

    # 物理存储指针
    filename: Path

    # 从 Frontmatter 解析
    node_type: str  # "plan" | "capture"
    parent_hint: Optional[str] = None

    # 文件主体内容
    content: str = ""

    # 从元数据或内容生成的单行摘要
    summary: str = ""

    # 所有者 ID，从 Git Ref 或数据库中填充
    owner_id: Optional[str] = None

    # --- 图遍历字段 (由加载器填充) ---
    parent: Optional[QuipuNode] = None
    children: List[QuipuNode] = dataclasses.field(default_factory=list)

    @property
    def short_hash(self) -> str:
        return self.output_tree[:7]

    @property
    def siblings(self) -> List[QuipuNode]:
        if not self.parent:
            return [self]
        return self.parent.children
