## [WIP] 修复在 `export` 命令重构过程中引入的 `NameError`

分析正确。测试失败的 traceback 给了我们明确的线索。

`NameError("name 'no_branch_link' is not defined")`

这是一个典型的重构错误。当我们将 `--no-branch-link` 选项重构为更通用的 `--hide-link-type` 选项时，我漏掉了一个地方，导致旧的、已被删除的变量 `no_branch_link` 仍然在一个函数调用中被使用。

### 错误分析
在 `packages/quipu-cli/src/quipu/cli/commands/export.py` 文件中，`_generate_file_content` 函数的签名已经更新为接收 `hidden_link_types: Set[str]`，但在其函数体内，调用 `_generate_navbar` 时，错误地传递了不存在的 `no_branch_link` 变量，而不是将新的 `hidden_link_types` 变量传递下去。

这导致了 `NameError`，进而使得 `export` 命令执行失败，所有相关的测试也因此失败。

### 用户需求
修复在 `export` 命令重构过程中引入的 `NameError`，使命令和所有相关测试能够正常通过。

### 评论
这是一个简单的修复，但它强调了在进行重构时，彻底检查所有相关代码路径（包括函数调用签名）的重要性。修复这个问题将使我们的新功能恢复健壮。

### 目标
1.  定位 `_generate_file_content` 函数中对 `_generate_navbar` 的错误调用。
2.  将传递的参数从 `no_branch_link` 修正为 `hidden_link_types`。
3.  确保所有测试用例都能通过。

### 基本原理
通过修正这个简单的变量名错误，我们将把正确的数据（需要隐藏的链接类型集合）传递给负责渲染导航栏的函数，从而修复整个逻辑链条。

### 标签
#intent/fix #flow/ready #priority/critical #comp/cli #concept/navigation #scope/core #ai/instruct #task/domain/cli #task/object/export-command #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 修正 `export.py` 中的变量名错误

我们将直接修正 `_generate_file_content` 函数中的那一行错误代码。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/export.py
~~~~~
~~~~~python
def _generate_file_content(
    node: QuipuNode,
    engine: Engine,
    no_frontmatter: bool,
    no_nav: bool,
    exported_hashes_set: Set[str],
    filename_map: Dict[str, str],
    hidden_link_types: Set[str],
) -> str:
    """构建单个 Markdown 文件的完整内容。"""
    parts = []
    if not no_frontmatter:
        parts.append(_format_frontmatter(node))

    public_content = engine.reader.get_node_content(node) or ""
    parts.append("# content.md")
    parts.append(public_content.strip())

    private_content = engine.reader.get_private_data(node.commit_hash)
    if private_content:
        parts.append("# 开发者意图")
        parts.append(private_content.strip())

    content_str = "\n\n".join(parts)

    if not no_nav:
        navbar_str = _generate_navbar(node, exported_hashes_set, filename_map, no_branch_link)
        content_str += navbar_str

    return content_str
~~~~~
~~~~~python
def _generate_file_content(
    node: QuipuNode,
    engine: Engine,
    no_frontmatter: bool,
    no_nav: bool,
    exported_hashes_set: Set[str],
    filename_map: Dict[str, str],
    hidden_link_types: Set[str],
) -> str:
    """构建单个 Markdown 文件的完整内容。"""
    parts = []
    if not no_frontmatter:
        parts.append(_format_frontmatter(node))

    public_content = engine.reader.get_node_content(node) or ""
    parts.append("# content.md")
    parts.append(public_content.strip())

    private_content = engine.reader.get_private_data(node.commit_hash)
    if private_content:
        parts.append("# 开发者意图")
        parts.append(private_content.strip())

    content_str = "\n\n".join(parts)

    if not no_nav:
        navbar_str = _generate_navbar(node, exported_hashes_set, filename_map, hidden_link_types)
        content_str += navbar_str

    return content_str
~~~~~

### 下一步建议
我们已经修复了 bug。现在请重新运行测试套件 (`pytest tests/cli/test_export_command.py`)。所有测试应该都会通过。确认无误后，我们就可以将这个功能作为一个完整的单元进行提交。
