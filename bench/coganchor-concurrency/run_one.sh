#!/bin/bash
# One rung of the ladder: N anchored agents of one backend, inside 16 CPUs and 64 GiB.
#
#   run_one.sh <backend> <concurrency>
#
# The cgroup is the whole of the constraint.  AllowedCPUs names eight physical cores and
# their siblings -- sixteen logical CPUs, which is what a 16-vCPU machine is -- so anything
# below that asks the kernel how wide it is gets the right answer.
set -u

BACKEND=$1
TMP=$(cd "$(dirname "$0")" && pwd)
N=$2
LAB=${LAB:-$TMP/lab}
ROOT=$(cd "$TMP/../.." && pwd)
PY=$ROOT/.venv/bin/python
MODEL_PORT=${MODEL_PORT:-18081}
TARGET_PORT=${TARGET_PORT:-18090}
BASE="http://127.0.0.1:$MODEL_PORT"
LISTENERS=${LISTENERS:-4}
ENDPOINTS=""
for n in $(seq 0 $((LISTENERS - 1))); do
  ENDPOINTS="$ENDPOINTS${ENDPOINTS:+,}tcp://127.0.0.1:$((TARGET_PORT + n))"
done
H="$LAB/homes/$BACKEND"
PATHS=${AGENT_PATH:-$HOME/.local/agents/bin:$HOME/.local/bin}:/usr/local/bin:/usr/bin:/bin

case "$BACKEND" in
claude)
  MODEL=claude-sonnet-4-5
  ENVS=(ANTHROPIC_BASE_URL="$BASE" ANTHROPIC_API_KEY=standin-key
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1) ;;
codex)
  MODEL=standin-1
  ENVS=(CODEX_HOME="$H/.codex" OPENAI_API_KEY=standin-key OPENAI_BASE_URL="$BASE/v1") ;;
grok)
  MODEL=standin-1
  ENVS=(XAI_API_KEY=standin-key) ;;
kimi)
  MODEL=standin/standin-1
  ENVS=(STANDIN_API_KEY=standin-key) ;;
dsh)
  MODEL=deepseek-chat
  ENVS=(DEEPSEEK_API_KEY=standin-key DEEPSEEK_BASE_URL="$BASE/v1") ;;
*) echo "unknown backend $BACKEND" >&2; exit 2 ;;
esac

# A scope takes no `LimitNOFILE`, and systemd hands it the stock 1024 soft limit against a
# 1048576 hard one.  Three descriptors per concurrent agent means that alone stops hmz at
# about 320 -- a real limit, and the first one anybody meets, but a fact about the login
# defaults rather than about the machine.  `NOFILE=1024` asks for it back.
exec sudo systemd-run --scope --quiet --uid="$(id -u)" --gid="$(id -g)" \
  -p AllowedCPUs=0-7,112-119 \
  -p MemoryMax=64G -p MemorySwapMax=0 -p TasksMax=infinity \
  -- /bin/sh -c 'ulimit -n "$1" || true; shift; exec "$@"' _ "${NOFILE:-1048576}" \
     env -i HOME="$H" PATH="$PATHS" TERM=dumb LANG=C.UTF-8 \
     HUMANIZE_SENTRY=off HUMANIZE_TELEMETRY=off \
     "${ENVS[@]}" \
     "$PY" $TMP/ramp.py \
       --backend "$BACKEND" --model "$MODEL" --concurrency "$N" \
       --lab "$LAB" --endpoint "$ENDPOINTS"
