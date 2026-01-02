import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

# Script configuration
ROOT_PATH = Path(__file__).parent.parent.resolve()
SRC_DIRS = [ROOT_PATH / "packages"]
LOCALES_PATH = ROOT_PATH / "packages/quipu-common/src/pyquipu/common/locales/zh"
BUS_METHODS = {"success", "info", "warning", "error", "get"}


class CodeVisitor(ast.NodeVisitor):
    """
    An AST visitor that finds all string literals passed as the first argument
    to `bus.<method>()` calls.
    """

    def __init__(self):
        self.keys = set()

    def visit_Call(self, node: ast.Call):
        # Pattern 1: bus.method("key.id", ...)
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "bus"
            and node.func.attr in BUS_METHODS
        ):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                key = node.args[0].value
                self.keys.add(key)

        # Pattern 2: QuipuResult(message="key.id", ...)
        elif isinstance(node.func, ast.Name) and node.func.id == "QuipuResult":
            for keyword in node.keywords:
                if (
                    keyword.arg == "message"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    key = keyword.value.value
                    self.keys.add(key)
                    break  # Found it, no need to check other keywords

        self.generic_visit(node)


def find_source_files(paths: list[Path]) -> list[Path]:
    """Find all .py files in the given source directories."""
    py_files = []
    for p in paths:
        py_files.extend(p.rglob("*.py"))
    return py_files


def extract_keys_from_code(source_files: list[Path]) -> set[str]:
    """Parse source files and extract localization keys."""
    visitor = CodeVisitor()
    for file_path in source_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
                tree = ast.parse(source_code, filename=str(file_path))
                visitor.visit(tree)
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"  - Warning: Could not parse {file_path.relative_to(ROOT_PATH)}: {e}", file=sys.stderr)
            continue
    return visitor.keys


def load_defined_keys(locales_path: Path) -> tuple[set[str], dict[str, list[str]]]:
    """Load all keys from JSON locale files and detect duplicates."""
    defined_keys = set()
    key_sources = defaultdict(list)

    if not locales_path.is_dir():
        print(f"Error: Locales directory not found at {locales_path}", file=sys.stderr)
        return set(), {}

    for json_file in locales_path.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key in data:
                    defined_keys.add(key)
                    key_sources[key].append(json_file.name)
        except json.JSONDecodeError as e:
            print(f"  - Warning: Could not parse JSON {json_file}: {e}", file=sys.stderr)

    duplicates = {key: files for key, files in key_sources.items() if len(files) > 1}
    return defined_keys, duplicates


def main():
    """Main execution function."""
    print("🚀 Starting localization string analysis...")
    has_errors = False

    # 1. Extract keys used in the source code
    print("\n1. Parsing source code to find used keys...")
    source_files = find_source_files(SRC_DIRS)
    used_keys = extract_keys_from_code(source_files)
    print(f"   => Found {len(used_keys)} unique keys used in the code.")

    # 2. Load keys defined in locale files
    print("\n2. Loading defined keys from locale files...")
    defined_keys, duplicates = load_defined_keys(LOCALES_PATH)
    print(f"   => Found {len(defined_keys)} unique keys defined in JSON files.")

    # 3. Analyze and report
    print("\n" + " Analysis Report ".center(50, "="))

    # Check for duplicates
    if duplicates:
        print("\n❌ ERROR: Duplicate keys found!")
        has_errors = True
        for key, files in sorted(duplicates.items()):
            print(f"  - Key '{key}' is defined in: {', '.join(files)}")

    # Check for missing keys (used but not defined)
    missing_keys = sorted(list(used_keys - defined_keys))
    if missing_keys:
        print("\n❌ CRITICAL: Missing keys! (Used in code but not defined in locales)")
        has_errors = True
        for key in missing_keys:
            print(f"  - {key}")

    # Check for unused keys (defined but not used)
    unused_keys = sorted(list(defined_keys - used_keys))
    if unused_keys:
        print("\n⚠️  WARNING: Unused keys found. (Defined in locales but not used in code)")
        for key in unused_keys:
            print(f"  - {key}")

    # Final summary
    if not has_errors and not unused_keys and not duplicates:
        print("\n✅ Success! All localization keys are consistent.")
    else:
        print("\n" + "".center(50, "="))

    if has_errors:
        print("\n🔥 Analysis finished with critical errors.")
        sys.exit(1)
    else:
        print("\n✨ Analysis finished.")
        sys.exit(0)


if __name__ == "__main__":
    main()
