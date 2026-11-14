#!/usr/bin/env bash
# Create a 32-byte key at $1 (mode 600) unless a file is already there. Refuses a path inside the
# repository. Never prints the key.
set -euo pipefail

key_file=${1:?usage: create-key.sh KEY_FILE}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)

if [[ -e $key_file ]]; then
    echo "Key exists at $key_file"
    exit 0
fi
umask 077
mkdir -p "$(dirname "$key_file")"
key_dir=$(cd "$(dirname "$key_file")" && pwd -P)
if [[ $key_dir/ == "$repo_root"/* ]]; then
    echo "refusing to write a key inside the repository: $key_file" >&2
    exit 3
fi
openssl rand -hex 32 >"$key_file"
chmod 600 "$key_file"
echo "Key written to $key_file"
