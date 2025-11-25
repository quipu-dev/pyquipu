# fix-test: Correct summary generation for plan nodes

## 用户需求
`test_full_workflow_with_git_object_storage` 测试用例在 `quipu log` 命令的输出验证环节失败。失败日志显示，`plan` 节点的摘要被错误地提取为 `~~~act`，而不是实际的指令内容 `write_file a.txt`。同时，测试用例本身也在断言一个错误的摘要内容。我需要修复摘要生成的逻辑和测试用例本身。

## 评论
经过分析，本次测试失败暴露了两个层面的问题：

1.  **逻辑缺陷**: 新的 `GitObjectHistoryWriter` 和旧的 `history.py` 在为 `plan` 节点生成摘要时，都存在逻辑缺陷。它们无法正确处理空的 `act` 指令块，或错误地将代码块的围栏符 (`~~~`) 识别为摘要内容。
2.  **测试用例不准确**: 测试用例中的断言是错误的，它期望在日志中找到文件的 *内容* (`File A content`)，而不是计划的 *摘要* (`write_file a.txt`)。

本次修复将通过统一并强化 `plan` 节点的摘要提取逻辑来解决第一个问题，确保它能准确地找到 `act` 块内的第一条有效指令。同时，我们也将修正测试用例，使其验证正确的、符合预期的摘要内容。

## 目标
1.  重构 `quipu.core.git_object_storage.GitObjectHistoryWriter` 中的 `_generate_summary` 方法，使其能够正确地从 `plan` 节点的 `content` 中提取 `act` 指令块内的第一行非空内容作为摘要。
2.  以同样的方式重构 `quipu.core.history.load_all_history_nodes` 中的摘要生成逻辑，以确保新旧两种存储后端在处理 `plan` 摘要时行为一致。
3.  修正 `tests/test_storage_integration.py` 中 `test_full_workflow_with_git_object_storage` 测试用例的断言，使其检查正确的摘要字符串。
4.  确保所有测试通过。

## 基本原理
`plan` 节点的摘要应反映其核心意图，这通常是 `act` 指令块中的第一条指令。我们将实现一个健壮的解析逻辑，该逻辑会：
1.  遍历计划内容（`content.md`）的每一行。
2.  当进入一个 `act` 块时，开始寻找第一个非空、非围栏符的行。
3.  一旦找到，就将其作为摘要并停止搜索。
4.  如果 `act` 块为空或未找到，则回退到一个默认值，如 "Plan executed"。

通过在 `GitObjectHistoryWriter` (用于新节点创建) 和 `history.py` (用于旧节点加载) 中应用相同的逻辑，我们保证了摘要生成的一致性。最后，校准测试用例以匹配这个正确的行为，将完成整个修复闭环。

## 标签
#comp/engine #comp/cli #concept/history #scope/tests

---

## Script

### Acts 1: 统一并修复 `plan` 节点摘要的生成逻辑

我们首先修复 `GitObjectHistoryWriter` 中的摘要生成逻辑。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~
~~~~~python
        if node_type == "plan":
            # 尝试从 Markdown 的第一个标题中提取
            match = re.search(r"^\s*#{1,6}\s+(.*)", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
            # 如果找不到标题，则从第一个非空行提取
            for line in content.strip().splitlines():
                clean_line = line.strip()
                if clean_line:
                    return (clean_line[:75] + '...') if len(clean_line) > 75 else clean_line
            return "Plan executed"
~~~~~
~~~~~python
        if node_type == "plan":
            # 优先从 act 块中提取摘要
            summary = ""
            in_act_block = False
            for line in content.strip().splitlines():
                clean_line = line.strip()
                if clean_line.startswith(('~~~act', '```act')):
                    in_act_block = True
                    continue
                
                if in_act_block:
                    if clean_line.startswith(('~~~', '```')):
                        break  # 块结束
                    if clean_line:
                        summary = clean_line
                        break  # 找到摘要
            
            if summary:
                return (summary[:75] + '...') if len(summary) > 75 else summary

            # 回退：尝试从 Markdown 的第一个标题中提取
            match = re.search(r"^\s*#{1,6}\s+(.*)", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
            
            return "Plan executed"
~~~~~

然后，在旧节点的加载逻辑 (`history.py`) 中应用相同的健壮逻辑。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/history.py
~~~~~
~~~~~python
            # For legacy nodes, we generate a summary on the fly.
            summary = "No description"
            if node_type == 'plan':
                # Simple heuristic: find the first non-empty line after `~~~act`
                in_act_block = False
                for line in body_content.strip().split('\n'):
                    if line.strip().startswith(('~~~act', '```act')): in_act_block = True; continue
                    if in_act_block and line.strip(): summary = line.strip(); break
                if not summary or summary in ('~~~', '```'): summary = "Plan executed"
            elif node_type == 'capture':
~~~~~
~~~~~python
            # For legacy nodes, we generate a summary on the fly.
            summary = "No description"
            if node_type == 'plan':
                # Robust heuristic: find the first non-empty, non-fence line inside `act` block
                in_act_block = False
                temp_summary = ""
                for line in body_content.strip().split('\n'):
                    clean_line = line.strip()
                    if clean_line.startswith(('~~~act', '```act')):
                        in_act_block = True
                        continue
                    if in_act_block:
                        if clean_line.startswith(('~~~', '```')):
                            break
                        if clean_line:
                            temp_summary = clean_line
                            break
                summary = temp_summary or "Plan executed"
            elif node_type == 'capture':
~~~~~

### Acts 2: 修正测试用例中的错误断言

最后，我们校准 `test_storage_integration.py` 中的测试用例，使其验证正确的摘要。

~~~~~act
replace
~~~~~
~~~~~path
tests/test_storage_integration.py
~~~~~
~~~~~python
        assert "add b.txt" in res_log.stderr  # Summary of the save message
        assert "File A content" in res_log.stderr # Summary of the plan
        
        # 4. Use `checkout` to go back to state A
~~~~~
~~~~~python
        assert "add b.txt" in res_log.stderr  # Summary of the save message
        assert "write_file a.txt" in res_log.stderr # Summary of the plan
        
        # 4. Use `checkout` to go back to state A
~~~~~