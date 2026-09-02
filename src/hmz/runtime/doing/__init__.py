"""Everything that can be asked of one workspace, composed out of the layers under it.

:class:`hmz.runtime.doing.core.Hmz` is the whole of it and the rest is what it hands back: the
flows there are, the accounts they run as, where a turn goes when the place taking it cannot,
the runs already made here and the run being made now. One directory rather than six modules
beside `runner` and `epic`, so that what composes the runtime is told apart at a glance from
what the runtime is made of -- and so that `epics.py`, the runs of a workspace, is never read
as `epic.py`, what one run is written down as.

Nothing here is a rule of its own. Each of these is the one place several ways in would
otherwise each have written the same answer, and every rule it is composing goes on being
written where it is carried out.

Reached through :mod:`hmz.runtime`, which is what a command line, a daemon and whoever is
calling humanize from outside all name.
"""
