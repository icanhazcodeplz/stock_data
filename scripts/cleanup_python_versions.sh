#!/usr/bin/env bash
set -euo pipefail

uv_python_dir="$HOME/.local/share/uv/python"

# All cpython versions managed by uv — any line whose path (direct or symlink target) is in the uv folder
all_installed=$(uv python list | grep "$uv_python_dir" | awk '{print $1}' | grep -oE '3\.[0-9]+\.[0-9]+[^-[:space:]]*' | sort -t. -k1,1n -k2,2n -k3,3n -u)

latest=$(echo "$all_installed" | grep '^3\.14\.' | tail -1)

if [[ -z "$latest" ]]; then
    echo "No installed Python 3.14.x versions found."
    exit 0
fi

to_remove=$(echo "$all_installed" | grep -v "^${latest}$")

echo "Keeping: $latest"

if [[ -z "$to_remove" ]]; then
    echo "Nothing else to remove."
    exit 0
fi

echo "Removing:"
echo "$to_remove"
echo "$to_remove" | xargs uv python uninstall
