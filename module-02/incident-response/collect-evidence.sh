#!/usr/bin/env bash
set -euo pipefail

# This wrapper exposes only the fixed GET-only evidence collector. It does not
# accept a command, query, URL, file path, or shell fragment from the caller.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$script_dir/responder.py" collect "$@"
