#!/bin/bash
# Climb the concurrency ladder for one backend until it stops behaving.
#
#   ladder.sh <backend> [max]
#
# A rung is "normal" when every agent on it finished its turn, said the sentence the scripted
# turn ends on, and left its work on the mock target.  The climb stops at the first rung that
# is not, and at the one after it -- one bad rung can be a fluke, two in a row is a ceiling.
set -u

BACKEND=$1
MAX=${2:-192}
TMP=$(cd "$(dirname "$0")" && pwd)
LAB=${LAB:-$TMP/lab}
OUT=${OUT:-$LAB/ladder-$BACKEND.jsonl}
[ "${APPEND:-0}" = 1 ] || : > "$OUT"

RUNGS=${RUNGS:-"1 2 4 8 16 24 32 48 64 96 128 160 192"}
bad=0
for n in $RUNGS; do
  [ "$n" -gt "$MAX" ] && break
  line=$(timeout 1800 bash "$TMP/run_one.sh" "$BACKEND" "$n" 2>/dev/null | tail -1)
  case "$line" in
    '{'*) ;;
    *) line="{\"backend\":\"$BACKEND\",\"concurrency\":$n,\"ok\":0,\"failed\":$n,\"errors\":[\"rung produced no summary\"]}" ;;
  esac
  echo "$line" >> "$OUT"
  echo "$line"
  failed=$(echo "$line" | python3 -c "import json,sys; print(json.load(sys.stdin).get('failed', -1))")
  if [ "$failed" != "0" ]; then
    bad=$((bad + 1))
    [ "$bad" -ge 2 ] && { echo "### $BACKEND: two bad rungs, stopping"; break; }
  else
    bad=0
  fi
done
echo "### $BACKEND ladder done -> $OUT"
