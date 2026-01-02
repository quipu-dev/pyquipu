Excellent, the script has done its job perfectly by identifying several concrete issues. The analysis is clear: we have duplicate definitions, a few missing keys, and a number of keys that appear to be unused.

Based on my analysis of the report, here's the plan:

*   **Duplicates:** The `acts.*` keys are defined in both `acts.json` and `runtime.json`. This is incorrect; they belong exclusively in `acts.json`. I will remove them from `runtime.json`.
*   **Missing Keys:** I will add the three missing keys to the correct locale files.
*   **Unused Keys:** This is the most interesting category. Many of these keys (like `run.success`, `engine.state.info.planNode`, etc.) seem like they *should* be in use. This is likely a limitation of the static analysis script: it can only find literal strings (e.g., `bus.success("key.id")`) but cannot trace keys passed through variables (e.g., `bus.success(result.message)`). Deleting these keys would be risky and likely break functionality.

Therefore, this plan will focus on fixing the definitive, critical errors: the duplicates and the missing keys.

## [WIP] fix: Correct localization key errors

### 错误分析

The script has identified three categories of problems:

1.  **重复的键 (Duplicate Keys)**: A significant number of keys with the `acts.` prefix were found in both `acts.json` and `runtime.json`. This indicates a copy-paste error during development. The single source of truth for these keys should be `acts.json`.
2.  **缺失的键 (Missing Keys)**: Three keys used in the codebase are not defined in any locale file, which would cause errors or display raw key IDs to the user.
3.  **未使用的键 (Unused Keys)**: The script reported many keys as unused. This is likely a **false positive**. The `ast` analysis is not sophisticated enough to track key names stored in variables (e.g., `result.message`). Deleting these keys would be unsafe. We will ignore this category for now and focus on the verifiable errors.

### 用户需求

The user wants to fix the localization issues reported by the `check_locales.py` script to improve codebase health and ensure all user-facing strings are correctly localized.

### 评论

This is a fantastic cleanup task. By fixing these issues, we make the codebase more maintainable, eliminate potential runtime errors from missing keys, and ensure each localization domain has a clear and single source of truth.

### 目标

1.  Remove all duplicate `acts.*` key definitions from `runtime.json`.
2.  Add the definition for `acts.basic.error.patchContentAmbiguous` to `acts.json`.
3.  Add definitions for `common.error.invalidConfig` and `run.warning.yoloEnabled` to `cli.json`.

### 基本原理

The strategy is to perform precise surgical fixes using `patch_file`. We will correct the verifiable errors (duplicates and missing keys) while deliberately avoiding the "unused keys" category due to the risk of false positives from the static analysis script. This ensures a safe and effective resolution of the most critical issues.

### 标签

#intent/fix #flow/ready #priority/high #comp/build #scope/dx #ai/refine #task/domain/testing #task/object/localization-checker #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 从 `runtime.json` 中移除重复的键

我们将从 `runtime.json` 文件中删除所有属于 `acts` 域的键，以解决重复定义的问题。

~~~~~act
patch_file
packages/quipu-common/src/pyquipu/common/locales/zh/runtime.json
~~~~~
~~~~~
    "runtime.plugin.error.loadFailed": "❌ 加载插件 {plugin_name} 失败: {error}",

    "acts.basic.success.fileWritten": "✅ [写入] 文件已写入: {path}",
    "acts.basic.success.filePatched": "✅ [更新] 文件内容已更新: {path}",
    "acts.basic.success.fileAppended": "✅ [追加] 内容已追加到: {path}",

    "acts.check.success.filesExist": "✅ [检查] 所有指定文件均存在。",
    "acts.check.success.cwdMatched": "✅ [检查] 工作区目录匹配: {path}",

    "acts.git.success.initialized": "✅ [Git] 已初始化仓库: {path}",
    "acts.git.success.added": "✅ [Git] 已添加文件: {targets}",
    "acts.git.success.committed": "✅ [Git] 提交成功: {message}",
    "acts.git.warning.repoExists": "⚠️  Git 仓库已存在，跳过初始化。",
    "acts.git.warning.commitSkipped": "⚠️  [Git] 没有暂存的更改，跳过提交。",

    "acts.memory.success.thoughtLogged": "🧠 [记忆] 思维已记录到 .quipu/memory.md",

    "acts.read.info.searching": "🔍 [搜索] 模式: '{pattern}' 于 {path}",
    "acts.read.info.useRipgrep": "⚡ 使用 'rg' (ripgrep) 进行高性能搜索。",
    "acts.read.info.noMatchRipgrep": "🤷 (rg) 未找到匹配项。",
    "acts.read.info.usePythonSearch": "🐢 使用原生 Python 搜索 (回退模式)。",
    "acts.read.info.noMatchPython": "🤷 (Python) 未找到匹配项。",
    "acts.read.info.readingFile": "📖 [读取] 正在读取 {filename}...",
    "acts.read.info.listingTree": "📂 [列表] 目录树: {path}",
    "acts.read.info.listingDir": "📂 [列表] 目录内容: {path}",
    "acts.read.warning.ripgrepFailed": "⚠️  ripgrep 执行出错，回退到 Python 搜索: {error}",
    "acts.read.error.readFailed": "❌ [读取] 无法读取二进制或非 UTF-8 文件: {filename}",

    "acts.refactor.success.moved": "✅ [移动] 已移动/重命名: {source} -> {destination}",
    "acts.refactor.success.deleted": "🗑️  [删除] 已删除: {path}",
    "acts.refactor.warning.deleteSkipped": "⚠️  文件不存在，跳过删除: {path}",

    "acts.shell.info.executing": "🚀 [Shell] 正在执行: {command}",
    "acts.shell.warning.stderrOutput": "⚠️  [Stderr]:\n{output}"
}
~~~~~
~~~~~
    "runtime.plugin.error.loadFailed": "❌ 加载插件 {plugin_name} 失败: {error}"
}
~~~~~

#### Acts 2: 修复缺失的键

现在，我们将缺失的键添加到它们各自正确的 JSON 文件中。

首先是 `acts.json`：

~~~~~act
patch_file
packages/quipu-common/src/pyquipu/common/locales/zh/acts.json
~~~~~
~~~~~
  "acts.basic.error.patchContentMismatch": "在文件 {path} 中未找到指定的旧文本。\n请确保 Markdown 块中的空格和换行完全匹配。",
  "acts.basic.error.patchPermission": "替换文件内容失败: 对 '{path}' 的访问权限不足。",
~~~~~
~~~~~
  "acts.basic.error.patchContentMismatch": "在文件 {path} 中未找到指定的旧文本。\n请确保 Markdown 块中的空格和换行完全匹配。",
  "acts.basic.error.patchContentAmbiguous": "在文件 {path} 中找到 {count} 个匹配项，无法确定要替换哪一个。",
  "acts.basic.error.patchPermission": "替换文件内容失败: 对 '{path}' 的访问权限不足。",
~~~~~

然后是 `cli.json`：

~~~~~act
patch_file
packages/quipu-common/src/pyquipu/common/locales/zh/cli.json
~~~~~
~~~~~
{
  "common.error.generic": "❌ 系统错误: {error}",
  "common.error.fileNotFound": "❌ 错误: 找不到指令文件: {path}",
~~~~~
~~~~~
{
  "common.error.generic": "❌ 系统错误: {error}",
  "common.error.invalidConfig": "❌ 配置或参数无效: {error}",
  "common.error.fileNotFound": "❌ 错误: 找不到指令文件: {path}",
~~~~~

~~~~~act
patch_file
packages/quipu-common/src/pyquipu/common/locales/zh/cli.json
~~~~~
~~~~~
  "run.info.usageHint": "\n用法示例:\n  quipu run my_plan.md\n  echo '...' | quipu run",
  "run.error.ambiguousCommand": "💡 提示: 你是不是想执行 'quipu {command}' 命令？",
  "run.listActs.ui.header": "\n📋 可用的 Quipu 指令列表:\n",
~~~~~
~~~~~
  "run.info.usageHint": "\n用法示例:\n  quipu run my_plan.md\n  echo '...' | quipu run",
  "run.error.ambiguousCommand": "💡 提示: 你是不是想执行 'quipu {command}' 命令？",
  "run.warning.yoloEnabled": "⚠️  YOLO 模式已启用，将跳过所有确认步骤。",
  "run.listActs.ui.header": "\n📋 可用的 Quipu 指令列表:\n",
~~~~~

### 下一步建议

我们已经修复了所有已确认的错误。现在，我建议你：

1.  **再次运行检查脚本**: 执行 `python scripts/check_locales.py` 来确认所有的重复和缺失键问题都已解决。
2.  **提交变更**: 在确认无误后，我们可以将这些修复作为一个 `[COMMIT]` 计划提交。
3.  **改进脚本 (可选)**: 我们可以考虑改进 `check_locales.py`，使其能够识别更多间接使用的键（例如，通过正则表达式查找 `QuipuResult(message="...")` 的模式），以减少关于“未使用键”的误报。
