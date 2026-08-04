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

import os
import re
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "SENT",
    "about",
    "asked",
    "crash",
    "enabled",
    "held",
    "snag",
    "start",
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

#: What is registered to be asked when a report is being made, and nothing else: a callable
#: apiece, run at the moment of the report and never before. Under a lock, since a flow
#: registers from whichever thread it is running on and a crash is reported from another.
_ABOUT: dict[str, Callable[[], object]] = {}
_TELLING = threading.Lock()

#: Whether the SDK has been started here, so that two entry points in one process -- the
#: interface, and a flow it runs -- start it once. A list rather than a name that is rebound,
#: since what it holds is a thing that happens rather than a constant.
_started: list[bool] = []


def enabled() -> bool | None:
    """Whether humanize reports its own failures, and None while nobody has been asked.

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
    from hmz.settings import Settings

    return Settings().enable_sentry


def asked(*, enable_sentry: bool) -> None:
    """Writes down the answer, which is asked once and holds wherever humanize is run.

    Args:
      enable_sentry: What was answered.
    """
    from hmz.settings import Settings

    Settings().answers(enable_sentry=enable_sentry)
    if enable_sentry:
        start()


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
            release=_version(),
            before_send=_before_send,
            before_send_transaction=_before_send,
        )
    except Exception:  # noqa: BLE001 -- a reporter that cannot start reports nothing
        return False
    _started.append(True)
    return True


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
            written = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
        except yaml.YAMLError:
            continue  # one that will not write is one left out of the report
        scope.add_attachment(
            bytes=_plainer(written).encode("utf-8"), filename=f"{name}.yaml"
        )


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
    for gone in ("server_name", "user", "request", "modules"):
        event.pop(gone, None)
    for one in event.get("exception", {}).get("values", []):
        for frame in one.get("stacktrace", {}).get("frames", []):
            frame.pop("vars", None)
            frame.pop("pre_context", None)
            frame.pop("post_context", None)
            frame.pop("context_line", None)
            frame["abs_path"] = _plainer(str(frame.get("abs_path") or ""))
        one["value"] = _plainer(str(one.get("value") or ""))
    # Breadcrumbs are whatever anything logged on the way here, which is not a thing anybody
    # answered a question about.
    event.pop("breadcrumbs", None)
    return event


def _plainer(said: str) -> str:
    """One string, with what must not leave a machine taken out of it.

    Args:
      said: Whatever was about to be sent.

    Returns:
      It, with home directories, credentials in URLs and anything shaped like a key replaced
      -- and cut short, since a long string in a report is a file somebody pasted.
    """
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
