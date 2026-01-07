#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path

# --- Configuration ---

# Project root directory, calculated as the parent of the 'scripts' directory
ROOT_DIR = Path(__file__).resolve().parent.parent

# Source and destination directories
OLD_TESTS_DIR = ROOT_DIR / "tests"
PACKAGES_DIR = ROOT_DIR / "packages"

# Mapping from old test subdirectory names to new package names
MODULE_MAPPING = {
    "application": "quipu-application",
    "cli": "quipu-cli",
    "engine": "quipu-engine",
    "integration": "quipu-cli",  # Integration tests are mostly CLI-driven
    "runtime": "quipu-runtime",
}

# Heuristic to determine test type. Subdirectories in this set are considered integration tests.
INTEGRATION_MODULES = {"integration", "cli", "application"}


def cleanup_empty_dirs(path: Path):
    """Recursively delete empty directories from the bottom up."""
    if not path.is_dir():
        return

    print(f"\n--- Cleaning up empty directories in {path.relative_to(ROOT_DIR)} ---")
    # Walk from the bottom up to delete empty directories
    for root, dirs, files in os.walk(path, topdown=False):
        for d in dirs:
            dir_path = Path(root) / d
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    print(f"Removed empty directory: {dir_path.relative_to(ROOT_DIR)}")
            except OSError as e:
                print(f"Error removing {dir_path}: {e}", file=sys.stderr)


def main():
    """Main script logic."""
    print("--- Starting Test Suite Restructuring ---")

    if not OLD_TESTS_DIR.exists():
        print(f"'{OLD_TESTS_DIR.relative_to(ROOT_DIR)}' does not exist. Nothing to do.")
        return 0

    # Find all Python files to be moved
    test_files = sorted(list(OLD_TESTS_DIR.rglob("*.py")))
    if not test_files:
        print("No test files found to migrate.")
        return 0

    moved_count = 0
    for old_path in test_files:
        try:
            relative_path = old_path.relative_to(OLD_TESTS_DIR)

            # Ignore root __init__.py, it's not needed
            if relative_path.name == "__init__.py" and len(relative_path.parts) == 1:
                continue

            # Determine the module (e.g., 'engine', 'cli')
            module_key = relative_path.parts[0]
            if module_key not in MODULE_MAPPING:
                print(f"WARNING: No mapping found for '{module_key}'. Skipping '{old_path}'.", file=sys.stderr)
                continue

            package_name = MODULE_MAPPING[module_key]
            package_test_root = PACKAGES_DIR / package_name / "tests"

            # Determine test type and final path
            if old_path.name == "conftest.py":
                # Place conftest.py at the root of the new tests directory
                new_path = package_test_root / "conftest.py"
            else:
                test_type = "integration" if module_key in INTEGRATION_MODULES else "unit"
                # Keep the subdirectory structure beyond the top level
                sub_path = Path(*relative_path.parts[1:])
                new_path = package_test_root / test_type / sub_path

            # Ensure the destination directory exists
            new_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create __init__.py files along the new path if they don't exist
            # to ensure they remain importable packages.
            for part in new_path.parent.relative_to(package_test_root).parts:
                init_path = package_test_root.joinpath(*part.split('/')[:i+1], "__init__.py")
                if not init_path.exists():
                    init_path.touch()


            # Move the file
            shutil.move(str(old_path), str(new_path))
            moved_count += 1
            print(f"Moved: {old_path.relative_to(ROOT_DIR)} -> {new_path.relative_to(ROOT_DIR)}")

        except Exception as e:
            print(f"ERROR: Failed to process '{old_path}': {e}", file=sys.stderr)

    print(f"\n--- Migration Summary ---")
    print(f"Successfully moved {moved_count} files.")
    
    # After moving all files, clean up the old 'tests' directory
    # Note: A more robust cleanup would be to delete the 'tests' directory entirely
    # if we are confident everything was moved. For safety, we only remove empty subdirs.
    import os
    cleanup_empty_dirs(OLD_TESTS_DIR)
    # Final check on the root tests dir itself
    try:
        if not any(OLD_TESTS_DIR.iterdir()):
             OLD_TESTS_DIR.rmdir()
             print(f"Removed empty root directory: {OLD_TESTS_DIR.relative_to(ROOT_DIR)}")
    except OSError:
        pass # May fail if hidden files etc. remain, which is fine.

    print("\n--- Restructuring Complete ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())