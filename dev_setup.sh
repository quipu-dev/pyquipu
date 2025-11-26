#!/bin/bash
# shellcheck disable=SC2034

# Fhrsk (AyeL's private stack)
# Quipu Development Environment Setup for bash/zsh

# Get the absolute path of the script's directory
# This ensures that the script can be sourced from anywhere
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Define aliases
alias qs="$DIR/.envs/stable/bin/quipu"
alias qd="$DIR/.envs/dev/bin/quipu"
alias ruff="$DIR/.envs/dev/bin/ruff"

echo "✅ Quipu & Ruff aliases activated for the current session:"
echo "   qs   -> Stable Quipu (.envs/stable)"
echo "   qd   -> Dev Quipu    (.envs/dev)"
echo "   ruff -> Dev Ruff     (.envs/dev)"
