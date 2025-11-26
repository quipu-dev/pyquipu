# 📸 Snapshot Capture

检测到工作区发生变更。

### 📝 变更文件摘要:
```
packages/quipu-cli/src/quipu/cli/main.py           |  8 +--
 .../src/quipu/core/git_object_storage.py           | 10 ++--
 packages/quipu-engine/src/quipu/core/hydrator.py   | 30 +++++-----
 packages/quipu-engine/src/quipu/core/sqlite_db.py  |  2 +-
 .../quipu-engine/src/quipu/core/sqlite_storage.py  | 68 +++++++++-------------
 .../quipu-interfaces/src/quipu/core/storage.py     |  2 +-
 tests/test_hydration.py                            | 16 ++---
 tests/test_integration_v2.py                       |  2 +-
 tests/test_plugin_resilience.py                    |  2 +-
 tests/test_sqlite_reader.py                        | 36 ++++++------
 tests/test_sqlite_writer.py                        |  2 +-
 11 files changed, 85 insertions(+), 93 deletions(-)
```