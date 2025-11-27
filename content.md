好的，我们开始执行计划的第一阶段。

这是一个清晰、简单的任务。我们将修改核心接口包 `quipu-interfaces` 中的 `QuipuNode` 数据模型，为其添加 `commit_hash` 字段，并更新相关文档，从而为后续所有重构提供一个坚实的数据基础。

### fix: 增强 QuipuNode 数据模型以消除标识符模糊性

#### 用户需求
当前 `QuipuNode` 数据模型缺少一个明确的 `commit_hash` 字段，导致系统的不同部分通过解析 `filename` 属性来间接获取此信息。这是一种脆弱且不直观的设计。为了消除这种模糊性，我们需要直接在数据模型中添加 `commit_hash` 属性。

#### 评论
这是解决标识符模糊问题的核心第一步。通过让核心数据模型 `QuipuNode` 携带完整的身份信息，我们为上层模块提供了一个明确且稳定的 API，极大地降低了后续重构的复杂性。

#### 目标
-   在 `quipu.core.models.QuipuNode` 中添加一个名为 `commit_hash` 的新字段。
-   更新 `QuipuNode` 的文档字符串，明确 `commit_hash` 和 `output_tree` 的不同职责。
-   确保此更改不会破坏现有的类型定义。

#### 基本原理
数据模型应该作为系统内部信息传递的“唯一事实源”。一个 `QuipuNode` 实例代表了历史图谱中的一个具体事件（一个 Git Commit），因此它必须包含指向该事件的唯一标识符 (`commit_hash`)，以及该事件导致的文件系统状态快照的唯一标识符 (`output_tree`)。将这些信息显式化是消除隐式契约和提高代码可读性的关键。

#### 标签
#intent/refactor #flow/ready #priority/high
#comp/interfaces #concept/history #scope/api
#ai/instruct
#task/domain/storage #task/object/api-contract #task/action/refactor
#task/state/continue

---

### Script

#### Acts 1: 修改 `QuipuNode` 数据模型

我们将修改 `packages/quipu-interfaces/src/quipu/core/models.py` 文件，为 `QuipuNode` 添加 `commit_hash` 字段并更新文档。

`````act
patch_file
`````
`````path
packages/quipu-interfaces/src/quipu/core/models.py
`````
`````python
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
`````
`````python
@dataclasses.dataclass
class QuipuNode:
    """
    表示 Axon 历史图谱中的一个节点。

    这个数据类封装了从文件名和文件内容中解析出的所有元数据和状态信息。
    """

    # 核心标识符
    commit_hash: str  # Git Commit 哈希，代表历史图谱中的一个事件
    output_tree: str  # Git Tree 哈希，代表此次事件产生的文件系统状态快照
    input_tree: str   # Git Tree 哈希，代表此次事件的输入状态
    timestamp: datetime

    # 物理存储指针
    filename: Path
`````
