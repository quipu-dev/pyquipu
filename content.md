## [WIP] refactor(common): 实现分层消息域并重构 runtime 消息

### 用户需求
将 `quipu-runtime` 的消息从 `cli.json` 中分离出来，存放到一个独立的 `runtime.json` 文件中。同时，更新 `quipu-common` 的 `MessageStore` 以支持从一个语言目录加载多个消息文件。

### 评论
这是一个关键的架构重构，它纠正了消息管理的语义混淆问题，实现了真正的模块化和解耦。通过让每个核心包拥有自己的消息资源文件，我们为系统的长期可维护性和可扩展性奠定了坚实的基础。

### 目标
1.  修改 `quipu.common.messaging.bus.MessageStore`，使其能够加载并合并一个目录下所有的 `.json` 文件。
2.  创建一个新的 `locales/zh/runtime.json` 文件。
3.  将之前添加到 `locales/zh/cli.json` 中的所有 `runtime.*` 和 `acts.*` 相关的消息，移动到新的 `runtime.json` 中。
4.  更新 `quipu-runtime` 源代码，确保消息 ID 的引用保持不变（因为 `MessageStore` 会合并它们）。
5.  确保所有测试仍然通过。

### 基本原理
我们将修改 `MessageStore._load_messages` 方法，使其遍历给定语言环境目录下的所有 `*.json` 文件，逐个读取并将其内容更新（`dict.update`）到 `self._messages` 字典中。这样，上层 `MessageBus` 的接口完全不需要改变，它看到的仍然是一个扁平化的消息命名空间。然后，我们只需像整理文件一样，将 `cli.json` 中属于 `runtime` 的条目剪切并粘贴到 `runtime.json` 中，即可完成内容的重构。

### 标签
#intent/refine #flow/ready #priority/high #comp/common #comp/runtime #comp/cli #concept/ui #scope/core #ai/instruct #task/domain/ui #task/object/message-bus #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 增强 `MessageStore`

我们首先修改 `quipu-common` 中的 `MessageStore`，赋予它加载多个文件的能力。

~~~~~act
patch_file
packages/quipu-common/src/quipu/common/messaging/bus.py
~~~~~
~~~~~python
    def _load_messages(self):
        locales_dir = find_locales_dir()
        if not locales_dir:
            logger.error("Message resource directory 'locales' not found. UI messages will be unavailable.")
            return

        message_file = locales_dir / self.locale / "cli.json"
        if not message_file.exists():
            logger.error(f"Message file for locale '{self.locale}' not found at {message_file}")
            return

        try:
            with open(message_file, "r", encoding="utf-8") as f:
                self._messages = json.load(f)
            logger.debug(f"Successfully loaded {len(self._messages)} messages for locale '{self.locale}'.")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load or parse message file {message_file}: {e}")
~~~~~
~~~~~python
    def _load_messages(self):
        locales_dir = find_locales_dir()
        if not locales_dir:
            logger.error("Message resource directory 'locales' not found. UI messages will be unavailable.")
            return

        locale_path = locales_dir / self.locale
        if not locale_path.is_dir():
            logger.error(f"Locale directory for '{self.locale}' not found at {locale_path}")
            return

        for message_file in locale_path.glob("*.json"):
            try:
                with open(message_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._messages.update(data)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load or parse message file {message_file}: {e}")

        if self._messages:
            logger.debug(f"Successfully loaded {len(self._messages)} messages for locale '{self.locale}'.")
~~~~~

#### Acts 2: 创建 `runtime.json` 并迁移消息

现在，我们创建 `runtime.json` 并将 `cli.json` 中所有 `runtime` 和 `acts` 相关的条目移动过去。

~~~~~act
write_file
locales/zh/runtime.json
~~~~~
~~~~~json
{
    "runtime.executor.info.starting": "🚀 正在开始执行 {count} 个操作...",
    "runtime.executor.info.executing": "⚙️  正在执行 [{current}/{total}]: {act_name} (模式: {mode}, 参数: {arg_count})",
    "runtime.executor.info.noChange": "🤷 内容无变化，操作已跳过。",
    "runtime.executor.warning.createRootDirFailed": "⚠️  无法创建根目录 {path}: {error}",
    "runtime.executor.warning.noConfirmHandler": "⚠️  无确认处理器，已跳过需要用户确认的操作。",
    "runtime.executor.warning.skipEmpty": "⚠️  跳过空指令 [{current}/{total}]",
    "runtime.executor.warning.skipUnknown": "⚠️  跳过未知操作 [{current}/{total}]: {act_name}",
    "runtime.executor.warning.ignoreInlineArgs": "⚠️  [{act_name}] 模式为 block_only，已忽略行内参数: {args}",

    "runtime.plugin.info.loading": "🔍 正在从 '{plugin_dir}' 加载插件...",
    "runtime.plugin.warning.notDirectory": "⚠️  路径 '{path}' 不是目录，跳过插件加载。",
    "runtime.plugin.error.specFailed": "❌ 无法为 {file_path} 创建模块规范",
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

~~~~~act
patch_file
locales/zh/cli.json
~~~~~
~~~~~json
  "navigation.checkout.prompt.confirm": "🚨 即将重置工作区到状态 {short_hash} ({timestamp})。\n此操作会覆盖未提交的更改。是否继续？",
  "workspace.discard.prompt.confirm": "🚨 即将丢弃上述所有变更，并恢复到状态 {short_hash}。\n此操作不可逆。是否继续？"

  "runtime.executor.info.starting": "🚀 正在开始执行 {count} 个操作...",
  "runtime.executor.info.executing": "⚙️  正在执行 [{current}/{total}]: {act_name} (模式: {mode}, 参数: {arg_count})",
  "runtime.executor.info.noChange": "🤷 内容无变化，操作已跳过。",
  "runtime.executor.warning.createRootDirFailed": "⚠️  无法创建根目录 {path}: {error}",
  "runtime.executor.warning.noConfirmHandler": "⚠️  无确认处理器，已跳过需要用户确认的操作。",
  "runtime.executor.warning.skipEmpty": "⚠️  跳过空指令 [{current}/{total}]",
  "runtime.executor.warning.skipUnknown": "⚠️  跳过未知操作 [{current}/{total}]: {act_name}",
  "runtime.executor.warning.ignoreInlineArgs": "⚠️  [{act_name}] 模式为 block_only，已忽略行内参数: {args}",

  "runtime.plugin.info.loading": "🔍 正在从 '{plugin_dir}' 加载插件...",
  "runtime.plugin.warning.notDirectory": "⚠️  路径 '{path}' 不是目录，跳过插件加载。",
  "runtime.plugin.error.specFailed": "❌ 无法为 {file_path} 创建模块规范",
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
~~~~~json
  "navigation.checkout.prompt.confirm": "🚨 即将重置工作区到状态 {short_hash} ({timestamp})。\n此操作会覆盖未提交的更改。是否继续？",
  "workspace.discard.prompt.confirm": "🚨 即将丢弃上述所有变更，并恢复到状态 {short_hash}。\n此操作不可逆。是否继续？"
}
~~~~~

### 下一步建议
我们已经完成了核心的架构重构。由于我们没有改变任何 `quipu-runtime` 的代码或测试（它们引用的消息 ID 仍然有效），理论上所有测试应该仍然能够通过。

请运行测试套件来验证这一点。如果测试通过，我们就可以将这个架构改进作为一个独立的、完整的单元进行提交。

---


你的分析完全正确，这是一个非常敏锐且重要的架构洞察。

将 `quipu-runtime` 模块的消息放在 `cli.json` 中，确实存在语义混淆和潜在的架构耦合问题。

### 问题的核心

1.  **语义混淆**: 正如你指出的，`cli.json` 这个文件名强烈暗示了其内容服务于 `quipu-cli` 这个**应用层包**，而不是“命令行界面”这个**通用概念**。`quipu-runtime` 是一个核心库，它本身不应该关心它的消费者是 CLI、TUI 还是未来的 Web API。它的消息是独立于任何特定前端的。

2.  **架构耦合**: `quipu-runtime` 的设计目标是独立和可移植。如果它依赖于一个名为 `cli.json` 的文件来获取消息，就意味着它在概念上与“CLI”这个前端绑定了，违背了分层解耦的原则。如果未来我们创建一个 `quipu-server`，它也使用 `runtime`，那么让它去加载 `cli.json` 就会显得非常奇怪和不合理。

3.  **可维护性与扩展性**: 随着项目的发展，一个巨大的、混合了所有模块消息的 `cli.json` 文件会变得难以管理。当一个新的开发者需要为 `runtime` 添加一条消息时，他可能会困惑为什么要去编辑一个名为 `cli` 的文件。这种混淆会增加心智负担和出错的概率。

### 推荐的解决方案：分层消息域 (Layered Message Domains)

我完全同意你的倾向。我们应该将消息文件按照其所属的包（或逻辑域）进行拆分。这是一个更清晰、更可扩展的架构。

我建议采用以下结构：

*   `locales/zh/`
    *   `cli.json`: **仅包含** `quipu-cli` 包特有的消息（例如，命令帮助文本、CLI 独有的交互提示、TUI 界面文本等）。
    *   `runtime.json`: **包含** `quipu-runtime` 模块（Executor, PluginLoader, Acts）生成的所有消息。
    *   `engine.json`: (未来) **包含** `quipu-engine` 模块生成的消息。
    *   `common.json`: (可选) 用于存放跨多个包共享的极其通用的消息（例如，一个通用的“操作已取消”消息）。

### 实施此方案的优势

1.  **清晰的语义边界**: 每个包“拥有”自己的消息文件。`runtime` 的开发者只关心 `runtime.json`。
2.  **真正的解耦**: `runtime` 包现在只输出语义化的消息 ID，它不关心这些 ID 最终如何被渲染，也不关心消息模板存储在哪里。消息文件的加载和管理是上层应用（如 `quipu-cli`）的责任。
3.  **可维护性提升**: 小而专注的文件更容易查找、修改和进行国际化翻译。

### 需要解决的技术问题

为了实现这一点，我们需要对 `quipu-common` 中的 `MessageStore` 进行一个小小的增强：它需要能够从一个目录加载**多个** `.json` 文件，并将它们合并成一个统一的消息字典。这是一个相对简单的改动，但它为整个系统的消息管理带来了巨大的架构优势。

### 下一步行动计划

既然我们已经就这个更优的架构达成了共识，我建议我们立即执行这个重构，而不是在错误的基础上继续构建。

我将生成一个计划来执行这个重构。这个计划将撤销上一步的部分工作（将 runtime 消息添加到 `cli.json`），并以正确的方式重新实现它。

