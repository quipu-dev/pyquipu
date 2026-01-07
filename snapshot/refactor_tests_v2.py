import shutil
from pathlib import Path

# Final, correct mapping of test files into the source tree.
FILE_MAP = {
    # Application tests
    "tests/application/conftest.py": "packages/quipu-application/src/pyquipu/application/tests/conftest.py",
    "tests/application/test_controller.py": "packages/quipu-application/src/pyquipu/application/tests/unit/test_controller.py",
    "tests/application/test_utils.py": "packages/quipu-application/src/pyquipu/application/tests/unit/test_utils.py",
    # CLI tests
    "tests/cli/conftest.py": "packages/quipu-cli/src/pyquipu/cli/tests/conftest.py",
    "tests/cli/test_cache_commands.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_cache_commands.py",
    "tests/cli/test_cli_interaction.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_cli_interaction.py",
    "tests/cli/test_export_command.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_export_command.py",
    "tests/cli/test_navigation_commands.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_navigation_commands.py",
    "tests/cli/test_query_commands.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_query_commands.py",
    "tests/cli/test_unfriendly_paths.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_unfriendly_paths.py",
    "tests/cli/test_workspace_commands.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_workspace_commands.py",
    "tests/cli/test_tui_logic.py": "packages/quipu-cli/src/pyquipu/cli/tests/unit/tui/test_logic.py",
    "tests/cli/test_tui_reachability.py": "packages/quipu-cli/src/pyquipu/cli/tests/unit/tui/test_reachability.py",
    "tests/cli/test_view_model.py": "packages/quipu-cli/src/pyquipu/cli/tests/unit/tui/test_view_model.py",
    # Engine tests
    "tests/conftest.py": "packages/quipu-engine/src/pyquipu/engine/tests/conftest.py", # Root conftest moves to engine tests
    "tests/engine/test_branching.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_branching.py",
    "tests/engine/test_checkout_behavior.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_checkout_behavior.py",
    "tests/engine/test_config.py": "packages/quipu-engine/src/pyquipu/engine/tests/unit/test_config.py",
    "tests/engine/test_deduplication.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_deduplication.py",
    "tests/engine/test_engine.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_engine.py",
    "tests/engine/test_engine_memory.py": "packages/quipu-engine/src/pyquipu/engine/tests/unit/test_engine_memory.py",
    "tests/engine/test_git_db.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_git_db.py",
    "tests/engine/test_git_reader.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_git_reader.py",
    "tests/engine/test_git_writer.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_git_writer.py",
    "tests/engine/test_head_tracking.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_head_tracking.py",
    "tests/engine/test_navigation.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/test_navigation.py",
    "tests/engine/sqlite/test_hydrator.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/sqlite/test_hydrator.py",
    "tests/engine/sqlite/test_reader.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/sqlite/test_reader.py",
    "tests/engine/sqlite/test_reader_integrity.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/sqlite/test_reader_integrity.py",
    "tests/engine/sqlite/test_writer.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/sqlite/test_writer.py",
    "tests/engine/sqlite/test_writer_idempotency.py": "packages/quipu-engine/src/pyquipu/engine/tests/integration/sqlite/test_writer_idempotency.py",
    # Runtime tests
    "tests/runtime/conftest.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/conftest.py",
    "tests/runtime/test_arg_strategy.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/test_arg_strategy.py",
    "tests/runtime/test_parser_and_basic_acts.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/test_parser_and_basic_acts.py",
    "tests/runtime/test_parser_auto_detect.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/test_parser_auto_detect.py",
    "tests/runtime/test_parser_robustness.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/test_parser_robustness.py",
    "tests/runtime/test_plugin_loader.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/test_plugin_loader.py",
    "tests/runtime/test_plugin_resilience.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/test_plugin_resilience.py",
    "tests/runtime/acts/test_check.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/acts/test_check.py",
    "tests/runtime/acts/test_git.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/integration/acts/test_git.py",
    "tests/runtime/acts/test_memory.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/acts/test_memory.py",
    "tests/runtime/acts/test_patch_ambiguity.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/acts/test_patch_ambiguity.py",
    "tests/runtime/acts/test_read.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/acts/test_read.py",
    "tests/runtime/acts/test_refactor.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/unit/acts/test_refactor.py",
    "tests/runtime/acts/test_shell.py": "packages/quipu-runtime/src/pyquipu/runtime/tests/integration/acts/test_shell.py",
    # Cross-package integration tests
    "tests/integration/conftest.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/sync/conftest.py",
    "tests/integration/test_cli_workflow.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_cli_workflow.py",
    "tests/integration/test_storage_selection.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_storage_selection.py",
    "tests/integration/test_sync_modes.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/sync/test_modes.py",
    "tests/integration/test_sync_workflow.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/sync/test_workflow.py",
    "tests/integration/test_workspace_invariance.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_workspace_invariance.py",
    "tests/integration/test_workspace_isolation.py": "packages/quipu-cli/src/pyquipu/cli/tests/integration/test_workspace_isolation.py",
}

def main():
    """Executes the test suite refactoring."""
    project_root = Path(__file__).parent.resolve()
    old_tests_root = project_root / "_tests_backup" # Use a temporary backup dir

    # Backup the old tests directory before cleaning
    if (project_root / "tests").exists():
        print("--- Backing up old 'tests' directory ---")
        shutil.move(project_root / "tests", old_tests_root)
        print(f"Backed up to {old_tests_root}")

    print("\n--- Moving test files to new structure ---")
    for old_path_str, new_path_str in FILE_MAP.items():
        # Source from the backup directory
        source_path = old_tests_root / old_path_str.replace("tests/", "", 1)
        dest_path = project_root / new_path_str

        if not source_path.exists():
            print(f"🟡 SKIPPED: Source file not found in backup: {source_path}")
            continue

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(source_path), str(dest_path))
            print(f"✅ MOVED: {old_path_str} -> {new_path_str}")
        except Exception as e:
            print(f"🔴 FAILED to move {source_path}: {e}")

    print("\n--- Creating __init__.py files ---")
    all_dirs = {p.parent for p in (project_root / new_path for new_path in FILE_MAP.values())}
    for d in all_dirs:
        # Create __init__.py in all parent directories up to the 'src' level
        curr = d
        while 'src' in curr.parts:
            init_file = curr / "__init__.py"
            if not init_file.exists():
                init_file.touch()
                print(f"✨ CREATED: {init_file.relative_to(project_root)}")
            if curr.name == 'src':
                break
            curr = curr.parent

    print(f"\n--- Cleaning up backup directory ---")
    shutil.rmtree(old_tests_root)
    print(f"Removed {old_tests_root}")

    print("\nRefactoring complete. Please update pyproject.toml files and then run 'pytest'.")

if __name__ == "__main__":
    main()
