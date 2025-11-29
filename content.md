分析得非常准确，你发现了关键问题。

日志中的第一行 `Failed to load or parse message file ... Invalid control character` 指出了根本原因：`locales/zh/cli.json` 文件存在一个 JSON 语法错误。

这个错误导致 `MessageBus` 无法加载任何消息模板，因此它只能回退到显示原始的消息 ID（例如 `<prompt.ui.diffHeader>`），这正是你在输出中看到的现象。

经过检查，问题出在 `cli.json` 文件的第二行，`"common.error.generic"` 消息的末尾缺少了一个右双引号 `"`，并且后面也缺少了逗号。

我将生成一个计划来修正这个语法错误。

## [WIP] fix: 修正 locales/zh/cli.json 中的 JSON 语法错误

### 错误分析
在执行 `qd run ruff.md` 时，程序因 `locales/zh/cli.json` 文件解析失败而无法正确显示用户界面消息。日志明确指出 JSON 文件在第 2 行存在语法错误。具体检查发现，`common.error.generic` 键对应的值字符串缺少闭合的双引号，并且该行末尾缺少了用于分隔下一个键值对的逗号。

### 用户需求
修复 `locales/zh/cli.json` 文件中的 JSON 语法错误，使 `MessageBus` 能够成功加载消息模板，从而让 CLI 能够正常渲染所有用户界面文本。

### 评论
这是一个阻断性的 Bug，必须立即修复，否则所有依赖 `MessageBus` 的 CLI 功能都将无法正常工作。这个修复将恢复 CLI 的可用性，并允许我们继续执行之前被中断的提交流程。

### 目标
1.  定位到 `locales/zh/cli.json` 中有语法错误的行。
2.  通过 `patch_file` 操作，为缺失的字符串添加闭合双引号和逗号。

### 基本原理
使用一个精确的 `patch_file` 指令，直接替换掉错误的一行，将其更正为语法正确的版本。这是修复此类简单文本错误的最高效、最直接的方法。

### 标签
#intent/fix #flow/ready #priority/critical #comp/cli #concept/ui #scope/dx #ai/instruct #task/domain/cli #task/object/message-bus #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 修正 `cli.json` 文件

我们将直接修正包含语法错误的那一行。

```````act
patch_file
locales/zh/cli.json
```````
```````json
  "common.error.generic": "❌ 系统错误: {error,
```````
```````json
  "common.error.generic": "❌ 系统错误: {error}",
```````

### 下一步建议
在执行完这个修复计划后，`locales/zh/cli.json` 文件应该就可以被正常解析了。

你可以再次运行 `qd run ruff.md` 来验证所有 UI 消息是否已正常显示。确认无误后，就可以安全地执行我之前生成的 `[COMMIT]` 计划，将所有 `MessageBus` 相关的重构工作提交到版本历史中。
