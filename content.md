# 📸 Snapshot Capture

检测到工作区发生变更。

### 📝 变更文件摘要:
```
packages/quipu-application/tests/__init__.py       |   0
 packages/quipu-application/tests/conftest.py       |  37 ++++
 packages/quipu-application/tests/unit/__init__.py  |   0
 .../tests/unit/test_controller.py                  | 109 ++++++++++
 .../quipu-application/tests/unit/test_utils.py     |  26 +++
 packages/quipu-cli/tests/__init__.py               |   0
 packages/quipu-cli/tests/conftest.py               |  13 ++
 packages/quipu-cli/tests/integration/__init__.py   |   0
 .../quipu-cli/tests/integration/sync/__init__.py   |   0
 .../quipu-cli/tests/integration/sync/conftest.py   |  38 ++++
 .../quipu-cli/tests/integration/sync/test_modes.py | 126 +++++++++++
 .../tests/integration/sync/test_workflow.py        | 206 ++++++++++++++++++
 .../tests/integration/test_cache_commands.py       | 129 +++++++++++
 .../tests/integration/test_cli_interaction.py      |  34 +++
 .../tests/integration/test_cli_workflow.py         | 240 +++++++++++++++++++++
 .../tests/integration/test_export_command.py       | 200 +++++++++++++++++
 .../tests/integration/test_navigation_commands.py  |  73 +++++++
 .../tests/integration/test_query_commands.py       | 147 +++++++++++++
 .../tests/integration/test_storage_selection.py    | 189 ++++++++++++++++
 .../tests/integration/test_unfriendly_paths.py     | 165 ++++++++++++++
 .../tests/integration/test_workspace_commands.py   |  60 ++++++
 .../tests/integration/test_workspace_invariance.py |  77 +++++++
 .../tests/integration/test_workspace_isolation.py  |  76 +++++++
 packages/quipu-cli/tests/unit/__init__.py          |   0
 packages/quipu-cli/tests/unit/tui/__init__.py      |   0
 packages/quipu-cli/tests/unit/tui/test_logic.py    |  74 +++++++
 .../quipu-cli/tests/unit/tui/test_reachability.py  |  78 +++++++
 .../quipu-cli/tests/unit/tui/test_view_model.py    | 204 ++++++++++++++++++
 packages/quipu-engine/tests/__init__.py            |   0
 packages/quipu-engine/tests/conftest.py            |  34 +++
 ...
 119 files changed, 5505 insertions(+), 5471 deletions(-)
```