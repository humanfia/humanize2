from __future__ import annotations

import importlib
import subprocess
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import pytest
from pydantic import BaseModel

from hmz.agents import (
    DRIVEN,
    DshAgent,
    DshAgentConfig,
    DshSession,
    Unrecoverable,
    dsh,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


_REAL_HARNESS_TYPE = dsh._harness_type


@dataclass(slots=True)
class Notice:
    method: str
    payload: dict[str, Any]


class Subscription:
    def __init__(self, client: Client, session_id: str) -> None:
        self.client = client
        self.session_id = session_id
        self.notices: deque[Notice] = deque()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        pass

    def next(self) -> Notice:
        return self.notices.popleft()


class Client:
    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.prompts: list[tuple[str, str]] = []

    def subscribe_session_notifications(self, session_id: str) -> Subscription:
        return Subscription(self, session_id)

    def session_prompt(
        self,
        session_id: str,
        content_blocks: list[dict[str, Any]],
        *,
        notification_subscription: Subscription,
    ) -> str:
        prompt = str(content_blocks[0]["text"])
        self.prompts.append((session_id, prompt))
        message_id = f"message-{len(self.prompts)}"
        scripted = self.harness.scripts.popleft()
        notification_subscription.notices.extend(
            [
                event(
                    session_id,
                    "agent/inbox/spliced",
                    {"inserted": [{"id": message_id}]},
                ),
                *(event(session_id, kind, data) for kind, data in scripted),
                Notice("session.status", {"sessionId": session_id, "status": "idle"}),
            ]
        )
        return message_id


class Harness:
    made: ClassVar[list[Harness]] = []
    next_scripts: ClassVar[deque[list[tuple[str, dict[str, Any]]]]] = deque()

    def __init__(self, **config: object) -> None:
        self.config = config
        self.client = Client(self)
        self.scripts = type(self).next_scripts
        self.started = False
        self.closed = False
        type(self).made.append(self)

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True


def event(session_id: str, kind: str, data: dict[str, Any]) -> Notice:
    return Notice(
        "session.event",
        {"sessionId": session_id, "event": {"type": kind, "data": data}},
    )


def assistant(
    text: str,
    *,
    reasoning: str = "",
    usage: dict[str, int] | None = None,
    turn: int = 1,
) -> tuple[str, dict[str, Any]]:
    content = [
        *([{"type": "reasoning", "text": reasoning}] if reasoning else []),
        {"type": "text", "text": text},
    ]
    return (
        "assistant/message",
        {
            "turn": turn,
            "step": 1,
            "message": {"content": content},
            "usage": usage or {},
        },
    )


def completed(turn: int = 1) -> tuple[str, dict[str, Any]]:
    return "turn/end", {"turn": turn, "reason": {"kind": "completed"}}


@pytest.fixture(autouse=True)
def sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    Harness.made.clear()
    Harness.next_scripts.clear()
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh-home"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(dsh, "_harness_type", lambda: Harness)
    monkeypatch.setattr(dsh, "_runtime_args", lambda: ("/opt/dsh-runtime",))
    yield
    for harness in Harness.made:
        harness.close()


def configured(
    *,
    permission: str = "bypass",
    provider: str = "",
) -> DshAgentConfig:
    return DshAgentConfig(
        model="deepseek-v4-flash",
        effort="high",
        permission=permission,
        provider=provider,
    )


def native_dsh_files(
    tmp_path: Path, *, credentials: str = "", settings: str = ""
) -> Path:
    """Writes the two files the dsh Models page owns."""
    home = tmp_path / "dsh-home"
    home.mkdir(exist_ok=True)
    if credentials:
        saved = home / ".credentials.yaml"
        saved.write_text(credentials, encoding="utf-8")
        saved.chmod(0o600)
    if settings:
        (home / "settings.yaml").write_text(settings, encoding="utf-8")
    return home


@pytest.mark.parametrize("key", [None, "", "   "])
def test_native_readiness_requires_a_nonblank_api_key(
    key: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if key is None:
        monkeypatch.delenv("DEEPSEEK_API_KEY")
    else:
        monkeypatch.setenv("DEEPSEEK_API_KEY", key)

    assert not dsh.native_ready(tmp_path)
    assert Harness.made == []


def test_native_readiness_accepts_an_ambient_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ambient-key")

    assert dsh.native_ready(tmp_path)
    assert Harness.made == []


def test_native_readiness_accepts_a_key_saved_by_dsh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    native_dsh_files(tmp_path, credentials="DEEPSEEK_API_KEY: saved-key\n")

    assert dsh.native_ready(tmp_path)
    assert Harness.made == []


def test_native_readiness_treats_broken_configuration_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    native_dsh_files(tmp_path, settings="llm-deepseek: [not-a-mapping]\n")

    assert not dsh.native_ready(tmp_path)
    assert Harness.made == []


def test_dsh_is_a_public_driven_agent() -> None:
    assert DRIVEN["dsh"] == (DshAgent, DshAgentConfig)
    assert DshAgent(configured()).backend == "dsh"
    assert DshAgent.pursues
    assert isinstance(DshAgent(configured()).new(), DshSession)


def test_a_turn_streams_reasoning_text_tools_usage_and_one_result(
    tmp_path: Path,
) -> None:
    Harness.next_scripts.append(
        [
            (
                "assistant/chunk",
                {
                    "turn": 1,
                    "step": 1,
                    "chunk": {"type": "reasoning-delta", "text": "thinking"},
                },
            ),
            (
                "tool/call",
                {"turn": 1, "step": 1, "name": "bash", "arguments": '{"cmd":"pwd"}'},
            ),
            assistant(
                "done",
                reasoning="thinking",
                usage={
                    "inputTokens": 11,
                    "outputTokens": 7,
                    "cacheReadTokens": 3,
                    "cacheWriteTokens": 2,
                    "reasoningTokens": 5,
                },
            ),
            completed(),
        ]
    )
    session = DshAgent(configured()).new(tmp_path)

    events = list(session.stream("work"))

    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "thinking"),
        ("tool", 'bash {"cmd":"pwd"}'),
        ("text", "done"),
        ("result", "done"),
    ]
    result = events[-1]
    assert result.tokens == {"deepseek-v4-flash": 23}
    assert dict(result.spent) == {
        "input": 11,
        "output": 7,
        "cache_read": 3,
        "cache_write": 2,
    }
    assert result.spent.total == 23  # reasoning is already inside output
    assert session.spent().total == 23


def test_follow_up_turns_resume_the_same_durable_session() -> None:
    Harness.next_scripts.extend(
        ([assistant("one"), completed()], [assistant("two", turn=2), completed(2)])
    )
    agent = DshAgent(configured())
    session = agent.new()

    assert session("first") == "one"
    session_id = session.id
    assert session("second") == "two"

    assert Harness.made[0].client.prompts == [
        (session_id, "first"),
        (session_id, "second"),
    ]
    assert agent.opened == [session_id]


def test_a_goal_uses_the_official_same_session_goal_tools() -> None:
    Harness.next_scripts.append(
        [
            assistant("still working"),
            completed(),
            assistant("done", turn=2),
            completed(2),
        ]
    )
    session = DshAgent(configured()).new()

    assert session.pursue("the suite passes") == "done"
    prompt = Harness.made[0].client.prompts[0][1]
    assert "create_goal" in prompt
    assert prompt.endswith("the suite passes")


def test_the_opening_session_id_is_visible_while_its_turn_is_running() -> None:
    Harness.next_scripts.append(
        [
            (
                "assistant/chunk",
                {
                    "turn": 1,
                    "step": 1,
                    "chunk": {"type": "text-delta", "text": "working"},
                },
            ),
            assistant("done"),
            completed(),
        ]
    )
    agent = DshAgent(configured())
    session = agent.new()
    streamed = session.stream("work")

    assert next(streamed).text == "working"
    opening = session.named
    assert opening is not None
    assert opening.startswith("session-")
    assert agent.opened == []

    assert [event.text for event in streamed] == ["done"]
    assert session.id == opening
    assert agent.opened == [opening]


def test_two_sessions_get_two_ids() -> None:
    Harness.next_scripts.extend(
        ([assistant("one"), completed()], [assistant("two"), completed()])
    )
    agent = DshAgent(configured())
    first, second = agent.new(), agent.new()

    first("first")
    second("second")

    assert first.id != second.id
    assert agent.opened == [first.id, second.id]


def test_a_failed_turn_is_common_failure_and_does_not_open_the_session() -> None:
    Harness.next_scripts.append(
        [
            assistant("partial"),
            (
                "turn/end",
                {
                    "turn": 1,
                    "reason": {
                        "kind": "error",
                        "error": {"message": "provider busy", "code": "SERVER"},
                    },
                },
            ),
        ]
    )
    agent = DshAgent(configured())
    session = agent.new()

    with pytest.raises(subprocess.CalledProcessError, match="dsh") as raised:
        session("work")

    assert raised.value.stderr.endswith("provider busy")
    assert session.named is None
    assert agent.opened == []
    # The turn failed, not the runtime behind it. Closing one that is still up is what
    # leaves a durable id with no live session under it, which every turn after this one
    # would be refused for as an id collision.
    assert not Harness.made[0].closed
    assert not isinstance(raised.value, Unrecoverable)


@pytest.mark.parametrize("reason", ["max-tokens", "blocked", "aborted", "interrupted"])
def test_every_non_completed_turn_end_is_a_failure(reason: str) -> None:
    Harness.next_scripts.append([("turn/end", {"turn": 1, "reason": {"kind": reason}})])

    with pytest.raises(subprocess.CalledProcessError):
        DshAgent(configured())("work")


def test_effort_changes_restart_the_runtime_but_resume_the_session() -> None:
    Harness.next_scripts.extend(
        ([assistant("one"), completed()], [assistant("two", turn=2), completed(2)])
    )
    session = DshAgent(configured()).new()
    session("first")
    session_id = session.id

    session.effort = "max"
    session("second")

    assert len(Harness.made) == 2
    assert Harness.made[0].closed
    assert [
        cast("dict[str, str]", one.config["env"])["HMZ_DSH_EFFORT"]
        for one in Harness.made
    ] == [
        "high",
        "max",
    ]
    assert Harness.made[1].client.prompts == [(session_id, "second")]


@pytest.mark.parametrize("effort", ["low", "ultra"])
def test_an_unsupported_effort_is_refused_before_startup(effort: str) -> None:
    agent = DshAgent(configured())
    agent.effort = effort

    with pytest.raises(ValueError, match="unsupported dsh effort"):
        agent("work")

    assert Harness.made == []


def test_permissions_the_sdk_cannot_enforce_are_refused() -> None:
    agent = DshAgent(configured(permission="read-only"))

    with pytest.raises(ValueError, match="permission must be 'bypass'"):
        agent("work")

    assert Harness.made == []


def test_a_missing_native_api_key_failure_reaches_watchers_with_setup_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    Harness.next_scripts.append(
        [
            (
                "turn/end",
                {
                    "turn": 1,
                    "reason": {
                        "kind": "error",
                        "error": {
                            "message": "no credential resolved for DEEPSEEK_API_KEY",
                            "code": "MISSING_CREDENTIAL",
                        },
                    },
                },
            )
        ]
    )
    agent = DshAgent(configured())
    heard: list[tuple[str, str]] = []
    agent.watch(lambda _agent, _session, event: heard.append((event.kind, event.text)))

    assert agent("hello", suppress=True) == ""

    failed = [text for kind, text in heard if kind == "failed"]
    assert len(failed) == 1
    assert "needs a DeepSeek API key" in failed[0]
    assert "Settings -> Models" in failed[0]
    assert "press a on its" in failed[0]
    assert len(Harness.made) == 1


def test_native_dsh_credentials_do_not_require_an_ambient_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    native_dsh_files(
        tmp_path,
        credentials="DEEPSEEK_API_KEY: saved-by-dsh\n",
        settings=("llm-deepseek:\n  baseURL: https://deepseek.example/v1\n"),
    )
    Harness.next_scripts.append([assistant("done"), completed()])

    assert DshAgent(configured()).new(tmp_path)("hello") == "done"

    assert Harness.made[0].config["env"] == {
        "DEEPSEEK_API_KEY": "saved-by-dsh",
        "DEEPSEEK_BASE_URL": "https://deepseek.example/v1",
        "HMZ_DSH_EFFORT": "high",
    }


def test_inherited_key_wins_while_dsh_settings_base_url_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "inherited-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://ambient.example")
    native_dsh_files(
        tmp_path,
        credentials="DEEPSEEK_API_KEY: stored-key\n",
        settings="llm-deepseek:\n  baseURL: https://saved.example\n",
    )
    Harness.next_scripts.append([assistant("done"), completed()])

    assert DshAgent(configured()).new(tmp_path)("hello") == "done"

    environment = cast("dict[str, str]", Harness.made[0].config["env"])
    assert environment["DEEPSEEK_API_KEY"] == "inherited-key"
    assert environment["DEEPSEEK_BASE_URL"] == "https://saved.example"


def test_custom_dsh_credential_reference_is_injected_for_the_bundled_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    native_dsh_files(
        tmp_path,
        credentials="MY_DEEPSEEK_KEY: custom-key\n",
        settings="llm-deepseek:\n  apiKeyEnv: MY_DEEPSEEK_KEY\n",
    )
    Harness.next_scripts.append([assistant("done"), completed()])

    assert DshAgent(configured()).new(tmp_path)("hello") == "done"

    environment = cast("dict[str, str]", Harness.made[0].config["env"])
    assert environment["DEEPSEEK_API_KEY"] == "custom-key"


def test_dsh_dotenv_fallback_prefers_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    home = native_dsh_files(
        tmp_path,
        settings="llm-deepseek:\n  apiKeyEnv: MY_DEEPSEEK_KEY\n",
    )
    (home / ".env").write_text("MY_DEEPSEEK_KEY=user-key\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("MY_DEEPSEEK_KEY='project-key'\n", encoding="utf-8")
    Harness.next_scripts.append([assistant("done"), completed()])

    assert DshAgent(configured()).new(project)("hello") == "done"

    environment = cast("dict[str, str]", Harness.made[0].config["env"])
    assert environment["DEEPSEEK_API_KEY"] == "project-key"


@pytest.mark.parametrize(
    ("document", "secret"),
    [
        ("DEEPSEEK_API_KEY: [secret-in-a-list]\n", "secret-in-a-list"),
        ("DEEPSEEK_API_KEY: [unterminated-secret\n", "unterminated-secret"),
        (
            "DEEPSEEK_API_KEY: first-secret\nDEEPSEEK_API_KEY: second-secret\n",
            "second-secret",
        ),
    ],
)
def test_invalid_dsh_credentials_fail_without_leaking_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: str,
    secret: str,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    native_dsh_files(tmp_path, credentials=document)

    with pytest.raises(ValueError, match="dsh credentials") as raised:
        DshAgent(configured()).new(tmp_path)("hello")

    assert secret not in str(raised.value)
    assert Harness.made == []


@pytest.mark.skipif(dsh.os.name == "nt", reason="POSIX permissions only")
def test_dsh_rejects_credentials_readable_by_other_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    home = native_dsh_files(tmp_path, credentials="DEEPSEEK_API_KEY: exposed-key\n")
    (home / ".credentials.yaml").chmod(0o644)

    with pytest.raises(ValueError, match="chmod 600"):
        DshAgent(configured()).new(tmp_path)("hello")

    assert Harness.made == []


@pytest.mark.parametrize("way", ["env", "gateway", "login"])
def test_only_a_key_provider_can_authenticate_dsh(
    way: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz import providers

    monkeypatch.delenv("DEEPSEEK_API_KEY")
    providers.add(
        "dsh",
        "legacy",
        way=way,
        env={"DEEPSEEK_API_KEY": "provider-key"},
    )
    agent = DshAgent(configured(provider="legacy"))
    heard: list[tuple[str, str]] = []
    agent.watch(lambda _agent, _session, event: heard.append((event.kind, event.text)))

    assert agent("hello", suppress=True) == ""

    assert [kind for kind, _text in heard].count("failed") == 1
    assert any("only supports API-key login" in text for _kind, text in heard)
    assert Harness.made == []


def test_shapes_are_asked_for_in_the_prompt() -> None:
    class Answer(BaseModel):
        done: bool

    Harness.next_scripts.append([assistant('{"done":true}'), completed()])
    session = DshAgent(configured()).new()

    assert session("decide", schema=Answer) == Answer(done=True)
    prompt = Harness.made[0].client.prompts[0][1]
    assert prompt.startswith("decide\n\nAnswer with JSON")
    assert '"done"' in prompt


def test_provider_environment_reaches_the_sdk_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz import providers

    monkeypatch.delenv("DEEPSEEK_API_KEY")
    providers.add(
        "dsh",
        "mine",
        way="key",
        env={"DEEPSEEK_API_KEY": "provider-key"},
    )
    Harness.next_scripts.append([assistant("done"), completed()])

    DshAgent(configured(provider="mine")).new(tmp_path)("work")

    made = Harness.made[0].config
    assert made["env"] == {
        "DEEPSEEK_API_KEY": "provider-key",
        "HMZ_DSH_EFFORT": "high",
    }
    assert made["cwd"] == str(tmp_path)
    launch = cast("tuple[str, ...]", made["launch_args_override"])
    assert launch[0].endswith("/env")
    assert launch[1:] == ("-u", "DEEPSEEK_BASE_URL", "/opt/dsh-runtime")
    assert made["request_timeout_seconds"] == 180.0


def failing(said: str) -> tuple[str, dict[str, Any]]:
    """One turn end that says the turn did not complete, in the runtime's own words."""
    return (
        "turn/end",
        {"turn": 1, "reason": {"kind": "error", "error": {"message": said}}},
    )


#: What the model answers a conversation that has outgrown it with, verbatim.
_OVERFLOWED = (
    "This model's maximum context length is 1048576 tokens. However, you requested "
    "1054143 tokens (798143 in the messages, 256000 in the completion). Please reduce "
    "the length of the messages or completion."
)

#: What the persistence layer answers a durable id whose live session is not the one it
#: was written by, which is what a runtime restarted under an adopted id produces.
_COLLIDED = (
    'session "session-abc" already has a persisted log on disk that does not match this '
    "live session (id collision)"
)


@pytest.mark.parametrize("said", [_OVERFLOWED, _COLLIDED])
def test_a_failure_no_other_try_could_change_is_said_once(said: str) -> None:
    """The two that made a long run a loop rather than a run that stopped.

    A conversation longer than the model takes is that long on the next try, and a durable
    id the runtime refuses as a collision is refused as one every time. Retried on an
    account's schedule, either is a flow that makes no progress and never ends.
    """
    Harness.next_scripts.append([failing(said)])

    with pytest.raises(Unrecoverable) as raised:
        DshAgent(configured())("work")

    assert said in str(raised.value)


def test_an_ordinary_failure_is_still_one_to_take_again() -> None:
    Harness.next_scripts.append([failing("provider is briefly unavailable")])

    with pytest.raises(subprocess.CalledProcessError) as raised:
        DshAgent(configured())("work")

    assert not isinstance(raised.value, Unrecoverable)


def test_a_turn_that_outgrew_the_model_is_taken_once_under_every_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop the report was about, from the outside: one failure, and one turn.

    A place that says a turn at it is worth taking again would otherwise take this one again
    on every rung of its chain of accounts, each try failing on the same words.
    """
    from hmz import fallbacks, providers

    tried_again = providers.Provider("dsh", providers.LOCAL, way="", fallback="second")
    second = providers.Provider("dsh", "second", way="")

    def chain(account: providers.Provider) -> list[providers.Provider]:
        return [account, second]

    monkeypatch.setattr(providers, "chain", chain)
    fallbacks.retrying(DshAgent(configured()).spec, 3, "none", 0.0)
    Harness.next_scripts.extend([failing(_OVERFLOWED)] for _ in range(8))
    agent = DshAgent(configured())
    monkeypatch.setattr(agent, "node", lambda: tried_again)

    with pytest.raises(Unrecoverable):
        agent("work")

    assert len(Harness.made[0].client.prompts) == 1


def test_a_flow_that_catches_its_own_turns_does_not_catch_this_one() -> None:
    """The loop the report was about, from the flow's side.

    `suppress=True` is the `|| true` a Ralph loop writes beside every call, and a `while True`
    that swallowed a failure no other try could come out differently on would go round on the
    same failure until somebody stopped it. So this one is not caught, for the reason a stop
    is not.
    """
    Harness.next_scripts.append([failing(_OVERFLOWED)])
    session = DshAgent(configured()).new()

    with pytest.raises(Unrecoverable):
        session("work", suppress=True)


def test_the_runtime_composition_compacts_before_the_model_refuses_the_turn() -> None:
    """A session that runs long enough must compact rather than overflow.

    Without this the first turn past the context window is where a loop driving one
    conversation stops for good: the next turn is the same conversation and the same
    refusal, and nothing in the composition ever makes it shorter.
    """
    cordis = dsh.importlib.resources.files("hmz.agents").joinpath("dsh.cordis.yml")
    composed = cordis.read_text()

    assert "@deepseek-ai/dsh-token-meter" in composed
    assert "@deepseek-ai/dsh-compaction-basic" in composed
    assert "auto: true" in composed


def test_the_runtime_composition_uses_only_plugins_bundled_with_the_sdk() -> None:
    cordis = dsh.importlib.resources.files("hmz.agents").joinpath("dsh.cordis.yml")
    configured_plugins = cordis.read_text()

    assert "@deepseek-ai/dsh-settings-file" not in configured_plugins
    assert "@deepseek-ai/dsh-credentials-local" not in configured_plugins


def test_a_missing_sdk_says_the_install_is_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken install rather than a choice made when humanize was installed.

    It is an ordinary dependency now, so there is no extra to have been left out of.
    """
    real_import = importlib.import_module

    def missing(name: str) -> object:
        if name == "deepseek_harness":
            raise ModuleNotFoundError(name=name)
        return real_import(name)

    monkeypatch.setattr(dsh, "_harness_type", _REAL_HARNESS_TYPE)
    monkeypatch.setattr(importlib, "import_module", missing)

    with pytest.raises(ModuleNotFoundError, match=r"humanize depends"):
        DshAgent(configured())("work")
