#!/usr/bin/env bash
# Convenience alias for upgrade.sh (canonical name is upgrade.sh).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/upgrade.sh" "$@"
