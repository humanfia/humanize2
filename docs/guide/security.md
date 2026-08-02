# Security

Three things about humanize are load-bearing and surprising. Read them before you point one at a
repository you care about.

## Every agent runs with permission prompts disabled

humanize drives coding agents unattended, as flowbench does, and **there is no setting that turns
the prompts back on**. An agent under a flow edits files, runs commands and makes commits without
asking.

[`/afk`](/features/afk) governs whether an agent may stop and ask you a *question*. It does not
govern whether it may act, and nothing does.

What you can narrow is [what an agent may do at all](/features/permissions) — one of four rungs,
set per agent:

```sh
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review this repository"
```

`bypass` is the default. `read-only` is the rung to reach for when you want a second agent to
look at a change without being able to touch it.

Drive a flow only in a workspace you are willing to have rewritten — including in
[a container of the agent's own](/features/containers), which confines the agent to that image
but mounts your workspace into it.

## A flow is a Python file, and reading one means running it

`-f` takes a Python file, and humanize imports it to find the `@flow` in it. Listing what a
[flowverse](/features/flowverses) holds imports **every** file in it.

So adding a flowverse is trusting that git repository with this machine, exactly as installing a
package is. Add the ones you would clone and run.

`builtin` and `official` are the two that are always there. `official` is
[humanfia/flowverse](https://github.com/humanfia/flowverse), and it is not fetched until
something wants what is in it.

## An `hmz anchor` port is equivalent to a shell on that machine

[Remote execution](/features/remote-execution) has three transports. Two of them need no open
port at all:

| Transport | What it is |
| --- | --- |
| `ssh://host` | bootstrapped over your own ssh. Nothing listens. |
| `docker://container` | over `docker exec`. Nothing listens. |
| `tcp://host:port` | an `hmz anchor serve` listening there. |

For the third: `--export` bounds which files a request may *name*; it does **not** confine the
commands that request can run. Anyone who can reach the port can run anything on that machine as
the user serving it.

- Give `--token` a real secret.
- Listening on anything but loopback with no token is refused outright.
- Prefer `ssh://` or `docker://`.

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

## What humanize does not hold

- **No API key.** It drives the CLI you already logged in; the credential goes from that CLI to
  its own provider.
- **No transcript of its own.** The backends write their own logs; a
  [cycle](/guide/concepts#cycle) records only which sessions belonged to which agent.
- **No values from a provider.** `hmz providers show` and `list` name the variables an account
  sets and never print what they are; a secret typed at the prompt is drawn as bullets and never
  shown again.

Provider credentials are copies of the CLI's own credential files, kept at `0600` in a directory
at `0700` under `~/.humanize/providers/`. A turn under a provider is run with the *other*
accounts' variables unset, so an `ANTHROPIC_API_KEY` left in a shell profile cannot silently
outrank the account the agent was told to run as.

## Reporting something

Open an issue at [humanfia/humanize2](https://github.com/humanfia/humanize2/issues). If it is a
vulnerability rather than a bug, say so in the title and leave the details out of the public
thread.
