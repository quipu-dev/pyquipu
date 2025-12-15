好的，已经确认测试通过。现在我们将本次功能实现作为一个完整的逻辑单元提交到版本控制。

我将生成一个 `[COMMIT]` 计划，其中包含 `git add` 和 `git commit` 指令。

## [COMMIT] feat(runtime): 支持带后缀的Markdown代码块语言标识符

### 用户需求
修改 Quipu 的解析器，使其能够正确识别 `python.old` 或 `python.new` 这种带有后缀的语言类型代码块。

### 评论
支持这种带有后缀的语言标识符，对于在计划中清晰地展示文件的不同版本（例如在 `patch_file` 操作中对比旧代码和新代码）非常有用。它增强了 AI 在生成计划时对代码块的描述能力和语义清晰度，从而提升人机协作的效率。

### 目标
1.  已修改 `packages/quipu-runtime/src/pyquipu/runtime/parser.py` 中 `RegexBlockParser` 的 `start_pattern` 正则表达式。
2.  已添加新的单元测试 `test_variable_lang_parser_recognition` 到 `tests/runtime/test_parser_and_basic_acts.py`，验证新格式代码块的正确解析。
3.  通过了所有相关测试。
4.  创建一个 Git 提交，将此功能持久化。

### 基本原理
通过调整正则表达式中的语言捕获部分，将其从 `(\w*)` 扩展为 `(\w*(?:\.\w+)*)`，使 `RegexBlockParser` 能够匹配包含点号和后缀的语言标识符。此修改是向后兼容的，并且增强了对多种内容块类型的识别能力。

### 标签
#intent/build #flow/ready #priority/high
#comp/runtime #comp/tests #concept/parser #scope/dx
#ai/instruct
#task/domain/runtime #task/object/parser #task/action/feature-extension #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交变更

现在，我们将修改后的文件添加到 Git 暂存区，并创建一个内容详尽的提交。

~~~~~act
git_add
packages/quipu-runtime/src/pyquipu/runtime/parser.py
~~~~~

~~~~~act
git_add
tests/runtime/test_parser_and_basic_acts.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
feat(runtime): support language identifiers with suffixes in Markdown blocks

This commit enhances the Markdown parser to correctly recognize and process fenced code blocks with language identifiers that include suffixes (e.g., `python.old`, `json.new`).

Previously, the `RegexBlockParser` in `quipu-runtime` used `(\w*)` for language capture, which only matched alphanumeric characters and underscores, failing to include dots. This meant that identifiers like `python.old` were truncated to `python`, and the suffix was ignored.

The `start_pattern` regex has been updated to `(\w*(?:\.\w+)*)` to allow for one or more dot-separated alphanumeric suffixes. This change:
- Enables more precise semantic labeling within Markdown plans, especially useful for `patch_file` operations that might display old and new versions of code.
- Improves the AI's ability to generate descriptive and semantically rich code blocks.
- Adds new test cases in `tests/runtime/test_parser_and_basic_acts.py` to ensure this functionality works correctly for both backtick and tilde parsers.
~~~~~

### 下一步建议
现在这个新功能已经提交，你可以尝试在未来的计划中使用 `python.old`、`python.new` 这样的代码块语言标识符来增强你的意图表达。例如，在进行 `patch_file` 操作时，可以在 `contexts` 中包含 `python.old` 和 `python.new` 块来清晰地展示修改前后的代码差异。
