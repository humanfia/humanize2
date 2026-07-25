# Remote execution

The agent process stays here, keeping its credentials, its state directory and its link to its
model provider. Everything it *does* — reading and writing files, running commands, reaching the
network from them — happens on the target. It needs no plugin and no cooperation from the agent:
Linux x86-64 here, and nothing but `python3` there.

```sh
amflows anchor --target ssh://build-box claude
amflows anchor --target ssh://gpu-01 codex exec "run the test suite"
```

`--target` takes `ssh://HOST`, `docker://CONTAINER`, `tcp://HOST:PORT` or `local[:DIR]`;
`--workspace` names the project directory as it exists on the target; `--check` connects, reports
what it found, and exits; `--shadow` puts the local mirror somewhere other than the workspace path.
A container is a target like any other: `docker://` runs the target half inside a running one
over `docker exec`, as whoever that container runs as, and needs no port and no secret.

`amflows.coganchor.connect` runs that same session from Python, taking those settings as an
`AnchorConfig` and returning the agent's exit status:

```python
from amflows.coganchor import AnchorConfig, connect

connect(
    ["claude", "--print"],
    AnchorConfig(target="ssh://build-box", workspace="/srv/project"),
)
```

`amflows.coganchor.check` is `--check` from Python: it returns what the target says about
itself, without running anything there.

## Anchoring a flow

Give an [agent](agents.md#machines)'s config an `anchor` and its agents work on another machine,
without any other change to the [flow](flows.md):

```python
from amflows.coganchor import AnchorConfig
from amflows.janus import ClaudeCodeAgentConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-4-8",
    effort="high",
    anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project"),
)
```

A turn that runs as its own process is anchored on its own, so a loop of short turns reaches the
target once per turn; a target left listening on `tcp://` makes that a socket rather than an ssh
session to bootstrap. A backend that holds one process across turns — Kimi Code, and Codex
pursuing a goal — is anchored once for the agent instead.

## Serving a target

Instead of reconnecting over ssh each time, a target can be left listening:

```sh
# on the target
amflows anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
# on this machine
AMFLOWS_TOKEN=$SECRET amflows anchor --target tcp://build-box:7777 --workspace /srv/project claude
```

Read [Security](../README.md#security) before opening one.
