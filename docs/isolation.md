# Isolation

Give an [agent](agents.md#machines)'s config an `isolation` and the agent brings its own machine: a
container of the image you name, holding this project directory at the path it already has and
running as you, so the work it leaves behind is yours in your own workspace and everything else is
the image's. It needs the `docker` command and a daemon to reach, on top of what
[remote execution](remote-execution.md) needs.

```python
from amflows.janus import ClaudeCodeAgentConfig
from amflows.janus.isolation import DockerIsolationConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-4-8",
    effort="high",
    isolation=DockerIsolationConfig(image="python:3.12"),
)
```

`workspace` gives the container a directory here other than this one.

The container starts on the agent's first turn, is shared by every session that agent launches,
and is removed when the agent is; each turn reaches it as a `docker://`
[target](remote-execution.md). The image needs a `python3` for coganchor's target half, and
whatever else the agent is expected to reach for. What it leaves behind is
[collected](tracing.md) by session.

A flow killed outright leaves its containers behind, labelled with the uid that started them:
`docker rm -f $(docker ps -q --filter label=amflows.janus=$(id -u))` clears yours.
