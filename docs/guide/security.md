# Security

Three things about humanize are load-bearing and surprising. Read them before you point one at
a repository you care about.

## Every agent runs with permission prompts disabled

humanize drives coding agents unattended, as flowbench does. **No setting turns the prompts
back on.** An agent under a flow edits files, runs commands and makes commits without asking.

[`/afk`](/guide/afk) governs whether an agent may stop and ask you a *question*. It does not
govern whether the agent may act. Nothing does.

You can narrow [what an agent may do at all](/guide/permissions). There are four rungs, set per
agent:

```sh
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review this repository"
```

`bypass` is the default. Reach for `read-only` when you want a second agent to look at a change
without being able to touch it.

Drive a flow only in a workspace you are willing to have rewritten. That includes [a container
of the agent's own](/guide/containers), which confines the agent to that image but mounts your
workspace into it.

## A flow is Python, and reading one means running it

`-f` takes a flow. humanize runs the flow's `__init__.py` to find the `@flow` in it. Listing
what a [flowverse](/guide/flowverses) holds imports **every** file in its `flows/`.

So adding a flowverse trusts that git repository with this machine, exactly as installing a
package does. Add the ones you would clone and run.

`builtin` and `official` are the two that are always there. `official` is
[humanfia/flowverse](https://github.com/humanfia/flowverse). humanize does not fetch it until
something wants what is in it.

## An `hmz anchor` port is equivalent to a shell on that machine

[Remote execution](/guide/remote-execution) has three transports. Two of them need no open port
at all:

| Transport | What it is |
| --- | --- |
| `ssh://host` | bootstrapped over your own ssh. Nothing listens. |
| `docker://container` | over `docker exec`. Nothing listens. |
| `tcp://host:port` | an `hmz anchor serve` listening there. |

For the third, `--export` bounds which files a request may *name*. It does **not** confine the
commands that request can run. Anyone who can reach the port can run anything on that machine
as the user serving it.

- Give `--token` a real secret.
- humanize refuses outright to listen on anything but loopback without a token.
- Prefer `ssh://` or `docker://`.

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

## What humanize does not hold

- **No API key.** humanize drives the CLI you already logged in. The credential goes from that
  CLI to its own provider.
- **No transcript of its own.** The backends write their own logs. A
  [cycle](/guide/concepts#cycle) records only which sessions belonged to which agent.
- **No values from a provider.** `hmz providers show` and `list` name the variables an account
  sets. They never print what those variables are. A secret you type at the prompt appears as
  bullets and never shows again.

Provider credentials are copies of the CLI's own credential files. humanize keeps them at
`0600` in a directory at `0700` under `~/.humanize/providers/`. A turn under a provider runs
with the *other* accounts' variables unset. So an `ANTHROPIC_API_KEY` left in a shell profile
cannot silently outrank the account the agent was told to run as.

## Reporting something

Open an issue at [humanfia/humanize2](https://github.com/humanfia/humanize2/issues). If it is a
vulnerability rather than a bug, say so in the title. Leave the details out of the public
thread.
