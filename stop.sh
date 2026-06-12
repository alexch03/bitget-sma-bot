#!/usr/bin/env bash
# Stop any python process running src.main or src.web from this repo.
set -uo pipefail

KILLED=0

# pkill -f matches against the full command line. Returns 1 if no process matched.
for pattern in "src\.main" "src\.web"; do
    # Count matches first so we can report
    COUNT=$(pgrep -f "$pattern" | wc -l | tr -d ' ')
    if [ "$COUNT" -gt 0 ]; then
        pkill -f "$pattern" || true
        KILLED=$((KILLED + COUNT))
    fi
done

if [ "$KILLED" -eq 0 ]; then
    echo "No running bot processes found."
else
    echo "Stopped $KILLED process(es)."
fi
