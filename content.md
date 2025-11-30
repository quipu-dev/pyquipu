# 📸 Snapshot Capture

检测到工作区发生变更。

### 📝 变更文件摘要:
```
bootstrap.py                                                |  3 +--
 packages/quipu-cli/src/pyquipu/cli/commands/axon.py         |  2 +-
 packages/quipu-cli/src/pyquipu/cli/commands/cache.py        |  4 ++--
 packages/quipu-cli/src/pyquipu/cli/commands/export.py       | 10 +++++-----
 packages/quipu-cli/src/pyquipu/cli/commands/helpers.py      |  5 ++---
 packages/quipu-cli/src/pyquipu/cli/commands/navigation.py   |  4 ++--
 packages/quipu-cli/src/pyquipu/cli/commands/query.py        |  8 ++++----
 packages/quipu-cli/src/pyquipu/cli/commands/remote.py       |  4 ++--
 packages/quipu-cli/src/pyquipu/cli/commands/run.py          |  6 +++---
 packages/quipu-cli/src/pyquipu/cli/commands/show.py         |  6 +++---
 packages/quipu-cli/src/pyquipu/cli/commands/ui.py           |  4 ++--
 packages/quipu-cli/src/pyquipu/cli/commands/workspace.py    |  4 ++--
 packages/quipu-cli/src/pyquipu/cli/controller.py            | 12 ++++++------
 packages/quipu-cli/src/pyquipu/cli/factory.py               | 10 +++++-----
 packages/quipu-cli/src/pyquipu/cli/logger_config.py         |  1 +
 packages/quipu-cli/src/pyquipu/cli/main.py                  |  6 ++++--
 packages/quipu-cli/src/pyquipu/cli/plugin_manager.py        |  1 +
 packages/quipu-cli/src/pyquipu/cli/rendering.py             |  1 +
 packages/quipu-cli/src/pyquipu/cli/tui.py                   | 13 ++++++-------
 packages/quipu-cli/src/pyquipu/cli/ui_utils.py              |  4 ++--
 .../quipu-common/src/pyquipu/common/messaging/__init__.py   |  2 +-
 packages/quipu-common/src/pyquipu/common/messaging/bus.py   |  3 +--
 .../quipu-common/src/pyquipu/common/messaging/messages.py   |  2 +-
 packages/quipu-engine/src/pyquipu/engine/config.py          |  5 +++--
 packages/quipu-engine/src/pyquipu/engine/git_db.py          | 13 +++++++------
 .../quipu-engine/src/pyquipu/engine/git_object_storage.py   |  2 +-
 packages/quipu-engine/src/pyquipu/engine/hydrator.py        |  4 ++--
 packages/quipu-engine/src/pyquipu/engine/sqlite_db.py       |  4 ++--
 packages/quipu-engine/src/pyquipu/engine/sqlite_storage.py  |  7 ++++---
 packages/quipu-interfaces/src/pyquipu/interfaces/models.py  |  5 +++--
 ...
 85 files changed, 224 insertions(+), 221 deletions(-)
```