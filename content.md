分析正确。测试失败了，而且失败的原因非常清晰地暴露了我之前实现中的逻辑缺陷。

错误分析
测试 `test_export_navbar_contextual_branch_link` 在 `Case 2` (`Node_Without_Sibling`) 中失败了。

1.  **失败的断言**: `assert "↓ [上一分支点]" in content_without_sibling`。测试期望一个在线性分支上、但源自一个分支历史的节点，**应该**有一个指向上级分支点的链接。但实际生成的导航栏中没有这个链接。

2.  **根本原因**: 我之前的实现 `if len(current_node.siblings) > 1:` 是一个过于简单和错误的判断。对于 `Node_Without_Sibling` 这个节点，它的父节点只有一个子节点（就是它自己），所以 `len(current_node.siblings)` 等于 1，导致 `if` 条件不满足，整个“上一分支点”的逻辑被跳过。

3.  **正确的逻辑**: 用户的意图不是检查“当前节点是否直接从一个分叉点长出来”，而是“当前节点是否处于一个更广泛的分支历史中”。因此，正确的逻辑不应该检查当前节点，而应该**向上追溯其祖先**，找到最近的分支点，并且只要那个分支点不是它的直接父节点（以避免与“父节点”链接冗余），就应该显示链接。

我的上一个 `patch_file` 实现是错误的。测试用例本身的设计是完全正确的，它成功地捕获了这个逻辑错误。

解决方案
我将修正 `export.py` 中的 `_generate_navbar` 函数，采用更健壮的逻辑：
1.  无条件地向上查找最近的、作为分支点的祖先节点。
2.  如果找到了这样的祖先，并且这个祖先不是当前节点的直接父节点，就创建“上一分支点”的链接。
3.  这个改动不需要修改测试文件，因为测试的预期是正确的。

## [WIP] fix(cli): 修正 export 导航栏分支点链接的生成逻辑

### 错误分析
在 `[WIP] test: 添加 export 导航栏上下文逻辑的专项测试` 中，`export.py` 的实现逻辑是错误的。它基于 `if len(current_node.siblings) > 1:` 来判断是否显示“上一分支点”链接，这导致了处于线性分支（但源于分支历史）的节点错误地丢失了该链接，从而导致 `test_export_navbar_contextual_branch_link` 测试失败。

### 用户需求
修正 `_generate_navbar` 函数，使其能正确地为所有处于分支历史中的节点生成“上一分支点”链接，同时避免该链接与“父节点”链接冗余。

### 评论
这是一个关键的逻辑修复。测试驱动开发在这里展现了它的价值：一个编写良好的测试用例精确地捕获了实现中的逻辑缺陷。修正这个问题将确保 `export` 功能的行为符合直觉且在所有情况下都保持一致。

### 目标
1.  修改 `packages/quipu-cli/src/quipu/cli/commands/export.py` 中的 `_generate_navbar` 函数。
2.  实现正确的逻辑：向上遍历祖先节点，找到第一个分支点，并且仅当该分支点不是当前节点的直接父节点时，才添加链接。
3.  确保 `test_export_navbar_contextual_branch_link` 测试现在能够通过，无需对测试本身进行任何修改。

### 基本原理
新的逻辑将更加健壮。它首先找到上下文中最相关的“上一个决策点”（即最近的祖先分支点），然后通过比较这个决策点与节点的直接父节点，来判断显示一个指向该决策点的链接是否有价值（即是否提供了父节点链接之外的新信息）。

### 标签
#intent/fix #flow/ready #priority/high #comp/cli #concept/navigation #scope/core #ai/instruct #task/domain/cli #task/object/export-navbar #task/action/refactor #task/state/continue

---

### Script

#### Acts 1: 修正 `export.py` 中的导航栏生成逻辑

我将使用正确的逻辑重写 `_generate_navbar` 函数中相关的部分。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/export.py
~~~~~
~~~~~python
    # 2. 上一分支点 (↓)
    # Per user request, only show this link if the current node is part of a branch (i.e., has siblings).
    # This avoids linking to distant, irrelevant branch points from a long linear history.
    if len(current_node.siblings) > 1:
        ancestor = current_node.parent
        while ancestor:
            if len(ancestor.children) > 1 and ancestor.commit_hash in exported_hashes_set:
                # To avoid redundancy, only add the link if the branch point is not the direct parent.
                # This handles cases where a node is an immediate child of a branch point.
                if current_node.parent and ancestor.commit_hash != current_node.parent.commit_hash:
                    nav_links.append(f"> ↓ [上一分支点]({filename_map[ancestor.commit_hash]})")
                break
            ancestor = ancestor.parent
~~~~~
~~~~~python
    # 2. 上一分支点 (↓)
    # Find the nearest ancestor that is a branch point.
    ancestor = current_node.parent
    found_branch_point = None
    while ancestor:
        if len(ancestor.children) > 1 and ancestor.commit_hash in exported_hashes_set:
            found_branch_point = ancestor
            break
        ancestor = ancestor.parent
    
    # Add the link only if a branch point was found AND it's not the direct parent
    # (to avoid a redundant link).
    if found_branch_point and current_node.parent and found_branch_point.commit_hash != current_node.parent.commit_hash:
        nav_links.append(f"> ↓ [上一分支点]({filename_map[found_branch_point.commit_hash]})")
~~~~~

### 下一步建议
我们已经修复了 `export.py` 中的逻辑错误。现在，请再次运行测试套件。如果所有测试都通过，我们就可以将这个功能标记为已完成，并准备创建一个 `[COMMIT]` 计划来合并所有相关的 `[WIP]` 节点。
