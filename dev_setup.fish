# Fhrsk (AyeL's private stack)
# Quipu Development Environment Setup for Fish Shell

# Get the absolute path of the script's directory
# This ensures that the script can be sourced from anywhere
set SCRIPT_PATH (status --current-filename)
set DIR (dirname "$SCRIPT_PATH")

# Define aliases
alias qs="$DIR/.envs/stable/bin/quipu"
alias qd="$DIR/.envs/dev/bin/quipu"
alias ruff="$DIR/.envs/dev/bin/ruff"

echo "✅ Quipu & Ruff aliases activated for the current session:"
echo "   qs   -> Stable Quipu (.envs/stable)"
echo "   qd   -> Dev Quipu    (.envs/dev)"
echo "   ruff -> Dev Ruff     (.envs/dev)"
