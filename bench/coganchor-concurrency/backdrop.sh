#!/bin/bash
# Everything the measurement needs that is NOT part of what is being measured:
#
#   * the stand-in model provider, which in production is a vendor's API
#   * `hmz anchor serve`, which in production is the target machine
#
# Both are started outside the constrained cgroup, deliberately: the question is how many
# anchored agents fit in 16 CPUs and 64 GiB, not how many agents plus the machine they are
# working on fit there.
set -u

TMP=$(cd "$(dirname "$0")" && pwd)
LAB=${LAB:-$TMP/lab}
ROOT=$(cd "$TMP/../.." && pwd)
MODEL_PORT=${MODEL_PORT:-18081}
TARGET_PORT=${TARGET_PORT:-18090}
SLOTS=${SLOTS:-192}
AB=${AGENT_BIN:-$(dirname "$(command -v kimi)")}

stop() {
  for pid in $(pgrep -f "standin_model[.]py" || true); do kill "$pid" 2>/dev/null || true; done
  for pid in $(pgrep -f "anchor serve --listen" || true); do kill "$pid" 2>/dev/null || true; done
  sleep 1
}

case "${1:-start}" in
stop) stop; echo "backdrop down"; exit 0 ;;
esac

stop
mkdir -p "$LAB/ws" "$LAB/tgt" "$LAB/homes" "$LAB/logs" "$LAB/runs"

# ---------------------------------------------------------------- the stand-in provider
STANDIN_LOG="$LAB/logs/standin.log" nohup python3 \
  $TMP/standin_model.py "$MODEL_PORT" \
  > "$LAB/logs/standin.out" 2>&1 &
sleep 1
curl -sS "http://127.0.0.1:$MODEL_PORT/v1/models" > /dev/null || { echo "standin failed"; exit 1; }

# ---------------------------------------------------------------- the mock controlled end
# One listener serves every session; its export table is fixed at start, so a slot for each
# concurrency level this rig will ever reach is declared up front.  The directories behind
# them are wiped and reseeded per run by ramp.py.
EXPORTS=()
for i in $(seq 0 $((SLOTS - 1))); do
  EXPORTS+=(--export "$LAB/ws/$i:$LAB/tgt/$i")
done
cd "$ROOT"
# Several listeners rather than one.  A listener is a Python process holding a thread per
# session, and one of those would eventually be the thing that runs out -- which would make
# the ceiling a fact about the stand-in rather than about the machine running hmz.
LISTENERS=${LISTENERS:-4}
for n in $(seq 0 $((LISTENERS - 1))); do
  port=$((TARGET_PORT + n))
  nohup ./.venv/bin/python -m hmz anchor serve --listen "127.0.0.1:$port" "${EXPORTS[@]}" \
    > "$LAB/logs/target-$port.out" 2>&1 &
done
sleep 8
for n in $(seq 0 $((LISTENERS - 1))); do
  port=$((TARGET_PORT + n))
  grep -q "listening" "$LAB/logs/target-$port.out" || {
    echo "target listener on $port failed:"; cat "$LAB/logs/target-$port.out"; exit 1; }
done

# ---------------------------------------------------------------- one HOME per backend
# Shared across that backend's concurrent agents, which is how humanize runs on a real
# machine: many agents, one user, one state directory each CLI keeps its sessions in.
BASE="http://127.0.0.1:$MODEL_PORT"

for backend in claude codex grok kimi dsh; do
  H="$LAB/homes/$backend"
  rm -rf "$H"; mkdir -p "$H"
done

# codex: a provider in its own home, so humanize's `codex app-server` finds it.
mkdir -p "$LAB/homes/codex/.codex"
cat > "$LAB/homes/codex/.codex/config.toml" <<TOML
model = "standin-1"
model_provider = "standin"
approval_policy = "never"
sandbox_mode = "danger-full-access"

[model_providers.standin]
name = "standin"
base_url = "$BASE/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
TOML

# grok: the same, plus a symlink to the already-unpacked binary so no session pays to
# decompress a 166 MB payload into a cold home.
mkdir -p "$LAB/homes/grok/.grok/bin"
ln -sf /home/ubuntu/.grok/bin/grok-1.0.13 "$LAB/homes/grok/.grok/bin/grok"
# And a `grok` on PATH that *is* the binary rather than the npm trampoline.  Anchored, the
# trampoline's exec of the real binary is routed to the target -- it is not on the list of
# programs coganchor keeps here as the agent's own runtime, the way Codex's are -- and grok
# then reports "Not signed in".  A tarball install looks exactly like this, so measuring
# through it measures grok rather than the trampoline.
mkdir -p "$LAB/bin"
ln -sf /home/ubuntu/.grok/bin/grok-1.0.13 "$LAB/bin/grok"
cat > "$LAB/homes/grok/.grok/config.toml" <<TOML
[cli]
installer = "npm"

[endpoints]
xai_api_base_url = "$BASE/v1"
cli_chat_proxy_base_url = "$BASE/v1"
TOML

# kimi: imported through its own non-interactive provider command, which is the only way in.
env -i HOME="$LAB/homes/kimi" PATH=/usr/bin:/bin:/usr/local/bin \
  "$AB/kimi" provider add --api-key standin-key "$BASE/api.json" > "$LAB/logs/kimi-provider.log" 2>&1
printf 'default_model = "standin/standin-1"\n' > "$LAB/homes/kimi/.kimi-code/head.toml"
cat "$LAB/homes/kimi/.kimi-code/head.toml" "$LAB/homes/kimi/.kimi-code/config.toml" \
  > "$LAB/homes/kimi/.kimi-code/config.new"
mv "$LAB/homes/kimi/.kimi-code/config.new" "$LAB/homes/kimi/.kimi-code/config.toml"
grep -q "standin" "$LAB/homes/kimi/.kimi-code/config.toml" || { echo "kimi provider import failed"; exit 1; }

echo "backdrop up: model on $MODEL_PORT, $LISTENERS mock targets from $TARGET_PORT, $SLOTS slots"
