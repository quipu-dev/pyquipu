#!/bin/bash

# ==============================================================================
# Quipu v1.0 to v1.1 Data Migration Script
#
# This script performs a one-way migration of Quipu's internal Git references
# to the new v1.1 format. It is designed for a single-user repository.
#
# WHAT IT DOES:
# 1. Deletes the SQLite cache (`.quipu/history.sqlite`) for a clean rebuild.
# 2. Finds all legacy commit heads from `refs/quipu/heads/*` and `refs/quipu/history`.
# 3. Creates new v1.1-compliant references at `refs/quipu/local/heads/<hash>`.
# 4. Deletes all legacy references.
#
# USAGE:
# 1. Place this script in the root of your Quipu project (where the .git dir is).
# 2. Run `chmod +x migrate_v1_to_v1.1.sh`.
# 3. Execute it: `./migrate_v1_to_v1.1.sh`.
# ==============================================================================

set -e # Exit immediately if a command exits with a non-zero status.

# --- Sanity Check ---
if [ ! -d ".git" ]; then
    echo "❌ Error: This script must be run from the root of a Git repository."
    exit 1
fi

echo "🚀 Starting Quipu v1.0 to v1.1 data migration..."
echo "----------------------------------------------------"

# --- Step 1: Delete the SQLite cache ---
DB_PATH=".quipu/history.sqlite"
if [ -f "$DB_PATH" ]; then
    echo "🗑️  Deleting old SQLite cache: $DB_PATH"
    rm -f "$DB_PATH"
else
    echo "✅ No existing SQLite cache found. Skipping deletion."
fi

# --- Step 2: Collect all unique legacy commit hashes ---
echo "🔍 Finding all legacy v1.0 references..."

# Using a temporary file to store unique hashes
TMP_HASHES_FILE=$(mktemp)

# Get hashes from refs/quipu/heads/*
git for-each-ref --format='%(objectname)' refs/quipu/heads/ > "$TMP_HASHES_FILE"

# Get hash from refs/quipu/history, if it exists
if git rev-parse --verify refs/quipu/history >/dev/null 2>&1; then
    git rev-parse refs/quipu/history >> "$TMP_HASHES_FILE"
fi

# Sort and get unique hashes
ALL_HASHES=$(sort -u "$TMP_HASHES_FILE")
rm "$TMP_HASHES_FILE"

if [ -z "$ALL_HASHES" ]; then
    echo "✅ No legacy Quipu references found. Nothing to migrate."
    exit 0
fi

# Use wc -l to count lines (hashes)
COMMIT_COUNT=$(echo "$ALL_HASHES" | wc -l | xargs)
echo "✅ Found ${COMMIT_COUNT} unique legacy commit heads to migrate."

# --- Step 3: Create new v1.1 references ---
echo "✍️  Creating new v1.1 references under 'refs/quipu/local/heads/'..."
for commit_hash in $ALL_HASHES; do
    NEW_REF="refs/quipu/local/heads/${commit_hash}"
    git update-ref "$NEW_REF" "$commit_hash"
    echo "   -> Created ${NEW_REF}"
done

# --- Step 4: Delete old v1.0 references ---
echo "🔥 Deleting old v1.0 references..."

# Delete all refs under refs/quipu/heads/
OLD_HEADS=$(git for-each-ref --format='%(refname)' refs/quipu/heads/)
if [ -n "$OLD_HEADS" ]; then
    for old_ref in $OLD_HEADS; do
        git update-ref -d "$old_ref"
        echo "   -> Deleted ${old_ref}"
    done
fi

# Delete refs/quipu/history if it exists
if git rev-parse --verify refs/quipu/history >/dev/null 2>&1; then
    git update-ref -d refs/quipu/history
    echo "   -> Deleted refs/quipu/history"
fi

echo "----------------------------------------------------"
echo "🎉 Migration complete!"
echo ""
echo "NEXT STEP:"
echo "Run 'quipu ui' or 'quipu cache rebuild' to regenerate the database from the migrated references."
echo ""