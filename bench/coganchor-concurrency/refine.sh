#!/bin/bash
# Narrow a backend's ceiling, keeping what the failures said.
#
#   refine.sh <backend> <rung> [rung...]
#
# The ladder finds the ceiling to within a wide step; this walks the gap in small ones and
# keeps stderr, which the ladder throws away and which is where a dying agent explains
# itself.
set -u

BACKEND=$1
shift
TMP=$(cd "$(dirname "$0")" && pwd)
LAB=${LAB:-$TMP/lab}
OUT=$LAB/refine-$BACKEND.jsonl
: > "$OUT"
mkdir -p "$LAB/logs"

for n in "$@"; do
  err=$LAB/logs/refine-$BACKEND-$n.err
  line=$(timeout 2400 bash "$TMP/run_one.sh" "$BACKEND" "$n" 2>"$err" | tail -1)
  case "$line" in '{'*) ;; *) line="{\"backend\":\"$BACKEND\",\"concurrency\":$n,\"ok\":0,\"failed\":$n}" ;; esac
  echo "$line" >> "$OUT"
  echo "$line" | python3 -c "
import json, sys
one = json.load(sys.stdin)
print(f\"{one['backend']:7} N={one['concurrency']:<4} ok={one['ok']:<4} failed={one['failed']:<4} \"
      f\"p95={one.get('turn_p95', -1)}s mem={one.get('peak_memory_gib', -1)}GiB \"
      f\"pids={one.get('peak_pids', -1)} cpu={one.get('cpu_busy_ratio', -1)} \"
      f\"target={one.get('target_busy_ratio', -1)}\")
"
  if [ -s "$err" ]; then
    echo "    stderr (first distinct lines):"
    sort -u "$err" | grep -viE "^\s*$" | head -4 | sed 's/^/      /'
  fi
done
echo "### $BACKEND refined -> $OUT"
