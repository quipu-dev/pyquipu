Of course. We have successfully implemented and stabilized the `quipu show` command through a series of iterative fixes. Now is the time to consolidate this work into a single, clean, and descriptive commit.

Based on your `git status` and the recent history, I will generate a `[COMMIT]` plan that stages all relevant changes and creates a comprehensive commit message.

## [COMMIT] feat(cli): implement robust `quipu show` command for node inspection

### 用户需求
A command was needed to inspect the internal contents of any history node, providing a way to view metadata, plans, and other generated files directly from the command line.

### 评论
The `quipu show` command is a crucial addition to the toolchain. It provides essential introspection capabilities, making it easier to debug issues, understand the system's state at any given point in history, and verify the contents of nodes. This significantly improves the developer experience and the overall transparency of the Quipu system.

### 目标
1.  A new command, `quipu show <hash>`, is implemented.
2.  The command supports a `--json` flag to output all node contents as a single JSON object.
3.  The command supports single or multiple uses of the `--extract` (`-e`) flag to output the raw, unmodified content of specific files.
4.  All previously identified bugs related to output (unwanted line numbers, content truncation, `NameError` crash, and unwanted reformatting) have been fixed.
5.  All related changes across the `cli`, `engine`, and `interfaces` packages are now formally committed to the repository.

### 基本原理
The feature is implemented as a new Typer command in `quipu-cli`. It leverages the `HistoryReader` interface (specifically `get_node_blobs`) to retrieve the raw binary content from the storage backend. The command's logic carefully distinguishes between different output modes: the default "pretty" view for terminals, a pure JSON object view for scripting, and a raw content extraction view that guarantees data integrity for piping and redirection. This series of fixes culminated in removing all `rich` text formatting from the `--extract` path to ensure output is pristine.

### 标签
#intent/build #intent/fix #intent/refactor #flow/ready #priority/high #comp/cli #comp/engine #comp/interfaces #concept/history #concept/ui #scope/api #scope/dx #ai/instruct #task/domain/cli #task/object/command-show #task/action/implementation #task/state/end #task/status/completed

---

### Script

#### Acts 1: Staging All Changes

First, we will add all the new and modified files to the Git staging area to prepare for the commit.

~~~~~act
git_add
packages/quipu-cli/src/quipu/cli/commands/show.py
packages/quipu-cli/src/quipu/cli/main.py
packages/quipu-engine/src/quipu/core/git_db.py
packages/quipu-engine/src/quipu/core/sqlite_storage.py
packages/quipu-interfaces/src/quipu/core/storage.py
~~~~~

#### Acts 2: Creating the Commit

Now, we will create the atomic commit that encapsulates the new feature and all its associated fixes.

~~~~~act
git_commit
~~~~~
~~~~~text
feat(cli): implement robust `quipu show` command for node inspection

Introduces the `quipu show <hash>` command, a new core utility for inspecting the internal contents of any history node. This command provides essential introspection and debugging capabilities.

Key features:
- View all file blobs within a node in a human-readable format.
- Support for `--json` output, which serializes all node files into a single JSON object for scripting and automation.
- Support for `--extract` / `-e` to output the raw, unmodified content of one or more specific files, making it pipe-friendly.

This commit also includes a series of fixes that ensure the command's output is reliable and adheres to standard CLI best practices:
- Fixed an issue where JSON output was prefixed with line numbers.
- Fixed content truncation caused by rich text formatting.
- Fixed a `NameError` crash due to a missing `List` type import.
- Reworked the `--extract` logic to completely remove rich text rendering, guaranteeing that the output is the pristine, original content from the Git blob.
~~~~~

### 下一步建议
With this feature now complete and committed, we can proceed with the main task of integrating the SQLite backend as the default storage mechanism, confident that we have the necessary tools to inspect our work.
