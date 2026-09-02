"""Which kind of failure stopped a turn, and what each kind is owed.

Before this there were two: a turn that failed and a turn no other try could come out
differently on. So a 401 was retried five times on a schedule, a `database is locked` waited a
minute for contention that clears in a second, and a rate limit was answered by asking the same
service again at once. Seven kinds now, each with an answer of its own -- and the answers are
the point, the names being only how one is looked up.

What is checked here is that what a CLI says is read as the kind it is, that the kind decides
how many goes the turn gets here, how long the shortest wait is and whether another account
answers it at all, that every step of it narrates itself as an event, and that a backend which
already knows is believed over any reading of a message.
"""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, fallbacks, providers
from hmz.coganchor.agents import AgentBase, AgentConfig, Event, Failed, Unrecoverable
from tests.stubs import ShellAgent, ShellSession
from tests.stubs import ShellAgent as _Shell

if TYPE_CHECKING:
    import os
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


@pytest.fixture
def accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home nothing has written to, `shell` as a backend, and two accounts of it."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    backends.remember("shell", ["sh"])
    providers.add("shell", "main", env={"WHOSE": "main"})
    providers.add("shell", "spare", env={"WHOSE": "spare"})
    providers.points("shell", "main", "spare")


@pytest.fixture
def unwaiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Waits that are worked out and narrated but not actually sat through.

    A rate limit waits half a minute on purpose, and a suite that sat through one per account
    would be a suite nobody runs. What the wait *was* is on the event that says it.
    """

    def slept(_seconds: float) -> None:
        """Waits nothing at all."""

    monkeypatch.setattr(time, "sleep", slept)


#: A turn that says something on stderr and fails, writing down which account took it -- so a
#: test reads both what the recovery said and how many goes each account actually got.
_SAYING = 'echo "${{WHOSE:-nobody}}" >> {at}; echo {said!r} >&2; exit 1'


def _took(tally: Path) -> list[str]:
    """Which account took each go, in order."""
    return tally.read_text(encoding="utf-8").split()


def _watched(agent: AgentBase) -> list[str]:
    """The lines a watcher would see the recovery itself narrated with.

    A command backend puts each line of the agent's own stderr on the stream as a `tool` too,
    which is what a person watching a turn wants and not what these are about. The recovery's
    own lines are the ones that name the backend they are about.

    Args:
      agent: The agent to watch.

    Returns:
      The list, filled as the turn runs.
    """
    narrated: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            narrated.append(event.text)
            if event.kind == "notice" and event.text.startswith(f"{agent.backend} ")
            else None
        )
    )
    return narrated


def _driving() -> tuple[ShellAgent, list[str]]:
    """An agent on `main`, and the lines a watcher would see its recovery narrated with."""
    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))
    return agent, _watched(agent)


def _fails(agent: ShellAgent, tally: Path, said: str) -> str:
    """Runs the failing turn and answers with what it finally failed with."""
    with pytest.raises(subprocess.CalledProcessError) as raised:
        agent.new()(_SAYING.format(at=tally, said=said))
    return str(raised.value)


def test_what_a_cli_says_when_it_stops_is_read_as_the_kind_it_is() -> None:
    """One classifier, because a 429 is a 429 whichever CLI was holding the socket."""
    read = {
        "Error: 429 Too Many Requests": "throttled",
        "RESOURCE_EXHAUSTED: quota exceeded for this project": "throttled",
        "Claude AI usage limit reached": "throttled",
        "API Error: 401 unauthorized": "refused",
        "Authentication required": "refused",
        "You are not logged into Antigravity.": "refused",
        "The model is not supported when using a ChatGPT account": "refused",
        "404 model not found: gpt-9": "retired",
        "SqliteError: database is locked": "contended",
        "Error: read ECONNRESET": "dropped",
        "FetchError: socket hang up": "dropped",
        "502 Bad Gateway": "dropped",
        "FATAL ERROR: Reached heap limit Allocation failed": "killed",
    }

    for said, fault in read.items():
        assert backends.trouble("claude", said) == fault, said


def test_a_failure_nothing_recognises_is_the_turn_that_has_always_failed() -> None:
    """The only answer that cannot be wrong about something it has not understood."""
    assert backends.trouble("claude", "the build is broken") == ""

    owed = fallbacks.answers("")
    assert owed.tries == 0  # the goes the place asked for, and no floor under them
    assert not owed.held
    assert owed.accounts  # and the account chain after them, as always
    assert not owed.policy  # waited the way the place says


def test_the_exit_status_says_it_where_the_process_never_got_to_speak() -> None:
    """A signal is not a sentence, and a shell's 127 is not one either."""
    assert backends.trouble("claude", "", status=127) == "missing"
    assert backends.trouble("claude", "", status=126) == "missing"
    assert backends.trouble("claude", "some earlier output", status=-9) == "killed"
    assert backends.trouble("claude", "", status=137) == "killed"


def test_what_one_cli_says_and_no_other_does_is_read_off_that_cli() -> None:
    """An SDK rather than a CLI: nothing about what dsh says reads like HTTP."""
    said = "DeepSeek Harness only supports API-key login and needs a DeepSeek API key."

    assert backends.trouble("dsh", said) == "refused"
    # And it is dsh's own: nothing else is taught to read that sentence.
    assert backends.trouble("claude", said) == ""


def test_a_cli_s_own_sentence_beats_a_word_that_happens_to_be_beside_it() -> None:
    """It knows what its own failure is; a shared signature only knows what a word is."""
    said = "dsh needs a DeepSeek API key -- set one, or your quota is spent"

    assert backends.trouble("dsh", said) == "refused"
    # The same line to a backend that has no sentence of its own reads as the word does.
    assert backends.trouble("claude", said) == "throttled"


def test_a_backend_that_reports_an_http_status_is_not_read_as_a_signal() -> None:
    """Kimi is driven through a daemon: what it reports is the status of the call it made."""
    assert backends.trouble("kimi", "rate limit exceeded", status=429) == "throttled"
    assert backends.trouble("kimi", "invalid api key", status=401) == "refused"
    assert backends.trouble("kimi", "model not found", status=404) == "retired"
    # No real HTTP status falls where a signal does, which is what tells the two apart.
    assert backends.trouble("kimi", "", status=137) == "killed"


def test_the_end_of_a_stream_is_what_is_read_rather_than_the_whole_of_it() -> None:
    """An agent asked to write a rate limiter says `rate limit` in prose for a page."""
    said = "rate limit rate limit\n" + ("the agent went on at length. " * 400)

    assert backends.trouble("claude", said) == ""


def test_a_backend_that_names_the_kind_itself_is_believed(accounts: None) -> None:
    """It knows something no signature does, so nothing here reads its message to guess."""
    failed = Failed(
        1, ["claude"], "", "some sentence nothing recognises", fault="killed"
    )
    session = ShellAgent(CONFIG).new()

    assert session._trouble(failed).fault == "killed"
    # And what was decided is written back, so the turn's own failure says it too.
    assert "(killed:" in str(failed)


def test_a_credential_that_was_refused_is_not_tried_again_under_it(
    accounts: None, tmp_path: Path
) -> None:
    """It is refused a minute later too, so five goes on a schedule is five minutes spent."""
    # Written down asking for three goes, which this failure is worth none of.
    fallbacks.retrying("shell@main/m", 3, "none", 0.0)
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    said = _fails(agent, tally, "API Error: 401 unauthorized")

    assert _took(tally) == ["main", "spare"]  # one go apiece, and straight on
    assert "was refused the credentials" in narrated[0]
    assert "that account needs signing in again" in narrated[0]
    assert "carrying on as spare" in narrated[0]
    assert "(refused: that account needs signing in again)" in said


def test_a_rate_limit_waits_long_and_then_walks_the_accounts(
    accounts: None, unwaiting: None, tmp_path: Path
) -> None:
    """The account is spending too fast; the next one is not spending at all."""
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    _fails(agent, tally, "Error: 429 Too Many Requests")

    # A go apiece beyond the first, even though nobody wrote a retry down: the wait is the
    # answer here, and a place with no tries would otherwise have had nowhere to put one.
    assert _took(tally) == ["main", "main", "spare", "spare"]
    assert "is rate-limited" in narrated[0]
    assert f"trying again in {fallbacks.THROTTLED:.0f}s" in narrated[0]
    assert "carrying on as spare" in narrated[1]


def test_the_time_a_place_was_given_still_holds_over_a_long_wait(
    accounts: None, tmp_path: Path
) -> None:
    """Checked before the wait, so a turn is never started knowing it is already spent."""
    fallbacks.retrying("shell@main/m", 1, "none", 0.5)
    tally = tmp_path / "took.txt"
    agent, _narrated = _driving()

    _fails(agent, tally, "Error: 429 Too Many Requests")

    # Half a second was all it had, and the wait a rate limit asks for is longer than that:
    # one go apiece, and no thirty seconds spent finding that out.
    assert _took(tally) == ["main", "spare"]


def test_a_model_that_is_gone_walks_no_account_of_that_cli(
    accounts: None, tmp_path: Path
) -> None:
    """They are all offered the same catalogue, so walking them is being told it four times."""
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    said = _fails(agent, tally, "404 model not found: m")

    assert _took(tally) == ["main"]
    assert (
        narrated == []
    )  # nowhere to carry on to, so nothing to narrate carrying on with
    assert "(retired: the model is gone" in said


def test_a_store_another_turn_had_open_is_tried_again_here_briefly(
    accounts: None, tmp_path: Path
) -> None:
    """Opencode keeps its sessions in one database shared across workspaces."""
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    _fails(agent, tally, "SqliteError: database is locked")

    # Three goes beyond the first, a second apart, and only then somewhere else.
    assert _took(tally).count("main") == 4
    assert "found its own store busy" in narrated[0]
    assert "trying again in 1s (1 of 3)" in narrated[0]


def test_a_dropped_connection_reopens_the_transport_and_resumes_the_conversation(
    accounts: None, tmp_path: Path
) -> None:
    """What was lost was the socket and not the session: the conversation is the backend's."""
    shut: list[str] = []

    class Reopening(ShellSession):
        """A session that says when what was holding its conversation open is let go of."""

        def _shut(self) -> None:
            shut.append(self._id or "")

    # Named for the backend it drives, as every agent here is: the class name is what says
    # which CLI this is, and a stand-in called anything else would be a backend of its own.
    class ShellAgent(_Shell):
        def new(self, cwd: str | os.PathLike[str] | None = None) -> Reopening:
            return Reopening(self, cwd)

    tally = tmp_path / "took.txt"
    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))
    narrated = _watched(agent)

    _fails(agent, tally, "Error: read ECONNRESET")

    assert shut  # let go of before the next go rather than spoken to again
    assert "lost the connection" in narrated[0]
    assert "reopening and resuming" in narrated[0]
    # And waited over the way the place says and no other way: there is nothing here to wait
    # out, the thing that failed having already gone.
    assert not fallbacks.answers("dropped").policy
    assert fallbacks.answers("dropped").least == 0.0


def test_a_cli_that_is_not_installed_says_which_line_installs_it(
    accounts: None,
) -> None:
    """A turn that failed for a missing CLI has nothing else worth saying."""

    class Gone(ShellSession):
        """A session whose command is not a command anything here has."""

        def _turn(self, prompt: str) -> tuple[list[str], str | None]:
            return (["definitely-not-installed-anywhere", prompt], None)

    class ClaudeCodeAgent(AgentBase):
        """Named for `claude`, so that the line it says is the line that installs claude."""

        def new(self, cwd: str | os.PathLike[str] | None = None) -> Gone:
            return Gone(self, cwd)

    with pytest.raises(subprocess.CalledProcessError) as raised:
        ClaudeCodeAgent(CONFIG).new()("hello")

    # A `CalledProcessError` rather than the `FileNotFoundError` the spawn actually raised: a
    # flow catches turns rather than transports, and a loop written against a failed turn
    # could not have carried on past anything else.
    assert "(missing: npm i -g @anthropic-ai/claude-code)" in str(raised.value)


def test_a_directory_that_has_gone_is_not_a_cli_that_is_not_installed(
    accounts: None, tmp_path: Path
) -> None:
    """Telling somebody to install a CLI they have is an answer to a question nobody asked."""
    session = ShellAgent(CONFIG).new()
    away = tmp_path / "gone"

    read = session._nothing_ran(FileNotFoundError(2, "No such file", str(away)))
    assert (
        read.fault == "missing"
    )  # a path that is not there and is not where the turn runs

    # And the directory the turn was to run in, which `subprocess` names instead of the
    # program when it is the chdir that failed.
    read = session._nothing_ran(FileNotFoundError(2, "No such file", session.cwd))
    assert (
        read.fault == ""
    )  # a failed turn nothing classified, tried again as any other is


def test_a_backend_that_keeps_its_reason_in_its_own_log_is_read_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Antigravity exits with a generic error and puts the status where nobody was looking."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    log = tmp_path / ".gemini/antigravity-cli/log"
    log.mkdir(parents=True)
    (log / "cli-20260910_070643.log").write_text(
        "I0910 07:06:43 client.go:88] rpc error: code = ResourceExhausted "
        "desc = HTTP 429: quota exceeded\n",
        encoding="utf-8",
    )

    # What the streams said is the generic error the evaluation saw six of.
    generic = "Agent execution terminated due to error."
    assert backends.trouble("agy", generic) == ""
    assert backends.trouble("agy", generic, journal=backends.journalled("agy")) == (
        "throttled"
    )


def test_a_log_nothing_has_written_to_lately_is_not_this_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log is appended to for as long as that CLI runs; an old one is another run's."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    log = tmp_path / ".gemini/antigravity-cli/log"
    log.mkdir(parents=True)
    (log / "cli-old.log").write_text("HTTP 429\n", encoding="utf-8")

    assert backends.journalled("agy", within=0.0) == ""
    # And a backend that keeps no such log never opens a file to find that out.
    assert backends.journalled("claude") == ""


def test_a_kind_answered_by_another_place_is_not_an_unrecoverable(
    accounts: None,
) -> None:
    """It is a turn with somewhere left to go, and `suppress` catches turns that failed."""
    session = ShellAgent(CONFIG).new()
    failed = Failed(1, ["sh"], "", "404 model not found", fault="retired")

    assert not isinstance(failed, Unrecoverable)
    assert not session._trouble(failed).accounts  # no account of it answers that
    assert session._trouble(failed).fault == "retired"


def test_a_turn_no_try_could_change_is_still_taken_once(
    accounts: None, tmp_path: Path
) -> None:
    """Whatever the kind says: a `while True` that swallowed one would never come out."""
    fallbacks.retrying("shell@main/m", 5, "none", 0.0)
    tally = tmp_path / "took.txt"

    class Once(ShellSession):
        """A backend that knows its own failure cannot come out differently, and says so."""

        def _result(self, transcript: str) -> Event:
            raise Unrecoverable(1, ["sh"], "", "429 too many requests")

    class ShellAgent(_Shell):
        def new(self, cwd: str | os.PathLike[str] | None = None) -> Once:
            return Once(self, cwd)

    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))
    with pytest.raises(Unrecoverable):
        agent.new()(f'echo main >> {tally}; echo "429 too many requests"')

    # Said once, though every signature in it reads as a rate limit and the place asked for
    # five more goes: a backend that knows its own failure is believed over any of that.
    assert _took(tally) == ["main"]


def test_a_suppressed_turn_still_says_which_kind_it_was(
    accounts: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Quiet on the answer, not on the reason: an account needing attention says so."""
    tally = tmp_path / "took.txt"
    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))

    assert (
        agent.new()(_SAYING.format(at=tally, said="401 unauthorized"), suppress=True)
        == ""
    )

    assert "(refused: that account needs signing in again)" in capsys.readouterr().err
