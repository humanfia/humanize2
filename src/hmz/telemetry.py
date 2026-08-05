"""What humanize reports about itself when something goes wrong, and what it never reports.

humanize is early. A crash on somebody else's machine is a crash nobody here sees, and an
interaction that reads as obvious to whoever wrote it and as nonsense to whoever met it is not
a crash at all -- so both are reported, and both are answered for once, by hand, on the first
start.

Two rules shape everything here.

**Nothing is sent that a person would be surprised by.** What a flow was told, what an agent
said back, what is in a file, what is in an account: none of it leaves this machine, and none
of it is reachable from what does. What is sent is the shape of a failure -- the exception and
where in humanize it happened -- and the shape of the run it happened in: which flow, which
backends at which models, which accounts by name, which skills by name. Names and never
values, counts and never contents. The three switches that would upload the rest are off and
say why where they are set.

**Nothing is sent that nobody said yes to.** The setting is `enable_sentry` and it has three
answers rather than two: on, off, and the absence that means nobody has been asked yet. Only
the interface asks, because only the interface has somebody to ask; a headless run reports if
the answer is already yes and is silent otherwise. `HUMANIZE_SENTRY=on|off` answers for one
process without writing anything down, which is what a scripted install and this suite use.

A leaf: it names nothing of humanize but the settings it reads and the home they are in, so
every layer may report and none of them has to be reached into to do it. What goes with a
report is the layers' own to say, and each says it by handing over a callable -- see
:func:`about` -- which is only ever run when a report is actually being sent.
"""

from __future__ import annotations

import contextlib
import os
import re
import sysconfig
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "SENT",
    "about",
    "again",
    "asked",
    "crash",
    "enabled",
    "held",
    "snag",
    "start",
    "stop",
]

#: Where the reports go. humanize's own project, and the one thing here that is not a
#: setting: a report that went somewhere else would be a report nobody who could fix it reads.
DSN = "https://cd097c311af7e8db070f593f62697d62@o4511914126344192.ingest.us.sentry.io/4511914131324928"

#: What answers the question for one process without writing anything down: `on` or `off`.
#: For a scripted install, for CI, and for this suite -- a run under it neither reports nor
#: asks, whatever the settings file says.
SAYS = "HUMANIZE_SENTRY"

#: What is sent, in the words the question is asked in and the words `/settings` repeats. This
#: is the promise: whatever is not on this list does not leave the machine, and the scrubbing
#: below is what keeps the list true rather than the list being what the scrubbing came to.
SENT = (
    "the error and where in humanize it happened",
    "which flow was running, and what each of its agents was set up to run",
    "which coding agents are installed here, and which accounts exist by name",
    "which skills and flowverses are in play, by name",
    "what humanize did that you then undid, refused or walked away from",
    "the version of humanize, of Python, and the kind of machine this is",
)

#: And what is not, in the same words. Written down rather than left to be inferred from the
#: first list: what somebody wants to know before answering is what humanize will not take.
KEPT = (
    "nothing you typed: no task, no prompt, no line at the prompt",
    "nothing an agent said, and nothing out of any transcript or session log",
    "no file, no path outside humanize itself, and no directory name",
    "no key, no token and no account credential -- not even the names of the variables",
)

#: How much of a string may be a path, a key or a sentence somebody typed. Everything that
#: reaches a report goes through this, however it got there.
_HOME = re.compile(r"/(?:home|homes|Users)/[^/\s:'\"]+")
_KEYS = re.compile(
    r"\b(?:sk|pk|ghp|gho|github_pat|xai|sk-ant|sk-proj)[-_][A-Za-z0-9_\-]{8,}\b"
)
_CREDS = re.compile(r"(?<=//)[^/\s@]+(?=@)")
_LONG = 500

#: What a failed command says of itself, which is the whole command line. A turn is a command,
#: and several of these backends are given the prompt as an argument of it -- so the one line
#: Python writes for a `CalledProcessError` is the task, verbatim, in the middle of an error
#: message. The status is what a report needs and the command is what it must not carry.
_RAN = re.compile(r"Command\s+'.*?'\s+(?=returned|timed out|died)", re.DOTALL)

#: The roots a report may name a file under: humanize's own package, and wherever Python keeps
#: what is installed beside it. A frame under one of them is named by its path under that root,
#: which is the whole of what a traceback needs and none of where this machine keeps things.
#: Settled once, since a traceback has thirty frames and this is per frame.
_ROOTS = tuple(
    at
    for at in dict.fromkeys(
        [Path(__file__).resolve().parent.parent]
        + [
            Path(said).resolve()
            for said in (
                sysconfig.get_paths().get("purelib"),
                sysconfig.get_paths().get("platlib"),
                sysconfig.get_paths().get("stdlib"),
            )
            if said
        ]
    )
)

#: What a frame is named where humanize does not recognise the file it is in. A traceback runs
#: through humanize, through what humanize is installed beside, and through whatever the person
#: running it wrote -- and the last of those is a file in their project, under a name they
#: chose, in a directory named after the work. The line it stopped at is worth having; the rest
#: of it is theirs.
_THEIRS = "<not humanize>"

#: What is registered to be asked when a report is being made, and nothing else: a callable
#: apiece, run at the moment of the report and never before. Under a lock, since a flow
#: registers from whichever thread it is running on and a crash is reported from another.
_ABOUT: dict[str, Callable[[], object]] = {}
_TELLING = threading.Lock()

#: Whether the SDK has been started here, so that two entry points in one process -- the
#: interface, and a flow it runs -- start it once. A list rather than a name that is rebound,
#: since what it holds is a thing that happens rather than a constant.
_started: list[bool] = []

#: What was written down about reporting, read once. The same shape and the same reason: this
#: is asked wherever a report might be made, which includes every key that did nothing.
_answered: list[bool | None] = []


def enabled() -> bool | None:
    """Whether humanize reports its own failures, and None while nobody has been asked.

    Read once and kept, since this is asked on paths that are hot: every key that does
    nothing is a `snag`, and a settings file parsed per keystroke is a settings file parsed
    per keystroke. What is written down is settled for the life of the process, which is
    what :func:`asked` and the settings menu say when they change it.

    Returns:
      What the environment says for this process, else what was written down, else None --
      which is a machine nobody has put the question to yet, and is not a no. Only the
      interface turns that into a question; everything else reads it as silence and reports
      nothing.
    """
    said = os.environ.get(SAYS, "").strip().lower()
    if said in ("on", "1", "true", "yes"):
        return True
    if said in ("off", "0", "false", "no"):
        return False
    if not _answered:
        from hmz.settings import Settings

        _answered.append(Settings().enable_sentry)
    return _answered[0]


def again() -> None:
    """Forgets what was read, for whoever has just written it down."""
    _answered.clear()


def asked(*, enable_sentry: bool) -> None:
    """Writes down the answer, which is asked once and holds wherever humanize is run.

    It also takes effect now. An answer of no from somebody who has been reporting all
    session is somebody saying stop, and a reporter that went on until the next start would
    be answering a question that was not asked.

    Args:
      enable_sentry: What was answered.
    """
    from hmz.settings import Settings

    Settings().answers(enable_sentry=enable_sentry)
    again()
    if enable_sentry:
        start()
    else:
        stop()


def start() -> bool:
    """Starts reporting, if it is on and has not been started already.

    Returns:
      Whether anything is reporting from here on. False for an answer that is no, for a
      machine nobody has been asked on, and for an SDK that will not start -- none of which
      is a reason to stop: humanize's own failures being unreported is a smaller thing than
      humanize not running.
    """
    if _started or not enabled():
        return bool(_started)
    try:
        import sentry_sdk
        from sentry_sdk.integrations.argv import ArgvIntegration
    except ImportError:  # pragma: no cover -- an install missing its own dependency
        return False
    try:
        sentry_sdk.init(
            dsn=DSN,
            # Off, though the quickstart line has it on. It attaches the address the report
            # was sent from, the name of this machine and the user at it -- and, in this SDK,
            # the variables of every frame of a stack, which here hold the task, the prompt,
            # the answer and whatever an account was configured with. It is the one switch
            # that would make a report say more about the person than about the failure.
            send_default_pii=False,
            # The same, said again where the SDK reads it separately: what is in a frame is
            # what humanize was working on, and what humanize works on is somebody's project.
            include_local_variables=False,
            # Off for the same reason: what humanize logs is paths, commands and the odd line
            # of what a backend wrote, and a log line is not a thing anybody consented to.
            enable_logs=False,
            # The machine is not named, and nor is the directory: a hostname is a person at a
            # company, and a working directory is the name of what they are building.
            server_name="",
            traces_sample_rate=1.0,
            profile_session_sample_rate=1.0,
            # Profiled while something is running rather than for the life of the process:
            # an interface sitting at a prompt is not work anybody needs a profile of.
            profile_lifecycle="trace",
            # The one default integration that would break the promise above: it attaches
            # `sys.argv`, and `hmz exec -f ralph_loop -a claude/... "$(cat TASK.md)"` puts the
            # whole task on it. Taken out here, and taken off again in `_before_send`, since a
            # switch this load-bearing is worth being wrong about twice.
            disabled_integrations=[ArgvIntegration()],
            release=_version(),
            before_send=_before_send,
            before_send_transaction=_before_send,
        )
    except Exception:  # noqa: BLE001 -- a reporter that cannot start reports nothing
        return False
    _started.append(True)
    return True


def stop() -> None:
    """Stops reporting for the rest of this process, whatever was started earlier.

    What is already on its way is left to go: a report of something that had already happened
    is not something an answer given afterwards can recall. Everything after this is silent,
    and `start()` would have to be asked again.
    """
    if not _started:
        return
    _started.clear()
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover -- an install missing its own dependency
        return
    # Closed rather than left holding a transport: an SDK that is still initialised is one
    # that would go on collecting whatever its integrations collect.
    with contextlib.suppress(Exception):
        sentry_sdk.get_client().close(timeout=1.0)
    with contextlib.suppress(Exception):
        sentry_sdk.init(dsn="")


def about(name: str, said: Callable[[], object]) -> None:
    """Says what to attach to a report, by handing over something that knows.

    The layers that know what a run is are above this one and must stay there, so what is
    attached is a callable rather than a value: a flow says how to describe itself, an
    interface says how to describe the machine, and neither is asked until a report is
    actually being sent. Which also means nothing is gathered on a machine that reports
    nothing.

    Args:
      name: What the attachment is called, which is the filename it arrives under.
      said: What to call for it. Anything it answers with is written as YAML and put through
        the same scrubbing everything else is. It must not raise; one that does is left out
        of the report rather than taking the report with it.
    """
    with _TELLING:
        _ABOUT[name] = said


def held() -> dict[str, object]:
    """Everything registered, asked now, for whoever is about to send or show a report.

    Returns:
      One entry per thing that answered, by name. A caller that raises is left out: a report
      that could not describe the run is still a report worth having.
    """
    with _TELLING:
        asking = dict(_ABOUT)
    found: dict[str, object] = {}
    for name, said in asking.items():
        try:
            found[name] = said()
        except Exception:  # noqa: BLE001, S112 -- one that cannot say is one left out
            continue
    return found


def crash(why: BaseException, **said: object) -> None:
    """Reports one failure, with everything the layers said about the run it happened in.

    Args:
      why: What went wrong.
      said: Anything else worth knowing, as short strings: what was being done, and by which
        part of humanize.
    """
    if not start():
        return
    import sentry_sdk

    with sentry_sdk.isolation_scope() as scope:
        for name, value in said.items():
            scope.set_tag(name, _plainer(str(value)))
        _attaches(scope)
        sentry_sdk.capture_exception(why)


def snag(name: str, **said: object) -> None:
    """Reports something that is not a failure and is not what anybody meant either.

    A key that did nothing, a menu answered and then thrown away, a line refused, a run
    stopped seconds after it started: none of it is an error, and all of it is somebody
    finding out that humanize does not work the way they expected. That is the half of the
    feedback a stack trace never carries, and on an early tool it is the more useful half.

    Args:
      name: What happened, as one hyphenated word -- `dead-key`, `changes-dropped`.
      said: What is worth knowing about it: counts, which sheet, which key. Never what was
        typed, and never what anything was called by anybody but humanize.
    """
    if not start():
        return
    import sentry_sdk

    with sentry_sdk.isolation_scope() as scope:
        scope.set_tag("snag", name)
        for held_, value in said.items():
            scope.set_tag(held_, _plainer(str(value)))
        _attaches(scope)
        sentry_sdk.capture_message(f"snag: {name}", level="warning")


def _attaches(scope: Any) -> None:
    """Puts what the layers said about the run onto one report.

    Args:
      scope: The scope the report is being made on.
    """
    import yaml

    for name, value in held().items():
        try:
            written = yaml.safe_dump(
                _plainly(value), sort_keys=False, allow_unicode=True
            )
        except yaml.YAMLError:
            continue  # one that will not write is one left out of the report
        scope.add_attachment(bytes=written.encode("utf-8"), filename=f"{name}.yaml")


def _plainly(said: object) -> object:
    """One thing to attach, with every string in it put through the scrubbing.

    Value by value rather than over the document: a document scrubbed as one string is a
    document that can be cut in half by the length limit, and half a YAML file is a file
    nobody can read.

    Args:
      said: Whatever a layer answered with.

    Returns:
      The same, with the strings in it plainer.
    """
    if isinstance(said, str):
        return _plainer(said)
    if isinstance(said, dict):
        return {
            str(_plainer(str(name))): _plainly(value)
            for name, value in cast("dict[object, object]", said).items()
        }
    if isinstance(said, (list, tuple)):
        return [_plainly(one) for one in cast("list[object]", said)]
    return said


def _before_send(event: Any, hint: Any) -> Any:
    """The last thing every report goes through, whoever made it.

    Belt as well as braces: the settings above already say that no frame carries its
    variables and that nothing about this machine or the person at it is attached, and this
    takes them off again -- an SDK that grows a new way of collecting one of them should find
    it taken away here rather than sent.

    Args:
      event: The report, as the SDK built it.
      hint: What it was built from, which is not read.

    Returns:
      The report to send, with what must not leave taken out of it.
    """
    del hint
    # `extra` is where the SDK's own integrations leave what they collected -- `sys.argv`
    # among them, which for `hmz exec` is the task. Nothing here puts anything in it, so the
    # whole of it goes rather than the parts of it anybody has thought of.
    for gone in ("server_name", "user", "request", "modules", "extra"):
        event.pop(gone, None)
    for one in event.get("exception", {}).get("values", []):
        for frame in one.get("stacktrace", {}).get("frames", []):
            frame.pop("vars", None)
            frame.pop("pre_context", None)
            frame.pop("post_context", None)
            frame.pop("context_line", None)
            _framed(frame)
        one["value"] = _plainer(str(one.get("value") or ""))
    # Breadcrumbs are whatever anything logged on the way here, which is not a thing anybody
    # answered a question about.
    event.pop("breadcrumbs", None)
    return event


def _framed(frame: dict[str, Any]) -> None:
    """One frame of a traceback, named the way a report may name it.

    A frame in humanize or in something humanize is installed beside is named by where it is
    under that root -- `hmz/agents/base.py`, `textual/app.py` -- which is what makes the report
    worth reading and says nothing about the machine it came off. A frame in anything else is a
    file of theirs: their flow, in their project, under names they chose. Its line number stays
    and the rest of it goes, because a directory named after the work is exactly what the
    promise above says humanize does not take.

    Args:
      frame: The frame, changed in place.
    """
    said = str(frame.get("abs_path") or frame.get("filename") or "")
    where = _under(said)
    if where is None:
        frame["abs_path"] = frame["filename"] = _THEIRS
        # The module and the function are named by whoever wrote the file, so they go with it.
        frame.pop("module", None)
        frame.pop("function", None)
        return
    frame["abs_path"] = frame["filename"] = where
    if frame.get("module"):
        frame["module"] = _plainer(str(frame["module"]))


def _under(said: str) -> str | None:
    """One file, as the path under whichever root humanize knows it by.

    Args:
      said: The file, as the SDK found it.

    Returns:
      Its path under that root -- so `hmz/telemetry.py` rather than wherever humanize is
      installed -- or None for a file under no root humanize knows, which is somebody's own.
    """
    if not said:
        return None
    try:
        at = Path(said).resolve()
    except (OSError, ValueError):  # pragma: no cover -- a path the OS will not settle
        return None
    for root in _ROOTS:
        if at.is_relative_to(root):
            return at.relative_to(root).as_posix()
    return None


def _plainer(said: str) -> str:
    """One string, with what must not leave a machine taken out of it.

    Args:
      said: Whatever was about to be sent.

    Returns:
      It, with home directories, credentials in URLs and anything shaped like a key replaced
      -- and cut short, since a long string in a report is a file somebody pasted.
    """
    said = _RAN.sub("A command ", said)
    said = _HOME.sub("~", said)
    said = _CREDS.sub("…", said)
    said = _KEYS.sub("…", said)
    return said if len(said) <= _LONG else said[:_LONG] + "…"


def _version() -> str:
    """What humanize this is, as the release a report is filed under."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return f"hmz@{version('hmz')}"
    except PackageNotFoundError:  # pragma: no cover -- a tree nobody installed
        return "hmz@unknown"
