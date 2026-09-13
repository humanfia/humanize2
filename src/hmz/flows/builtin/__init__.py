"""The flows humanize keeps in the package, which is `chat` and nothing else.

One agent talking: the flow an interface opens on, and the shortest thing there is that shows
what a flow is. It is here rather than in the
[official flowverse](https://github.com/humanfia/flowverse) because it is what humanize does
before anything has been fetched -- a machine that has never reached a network still has to
have something to open talking to, and a first run that had to clone before it could say hello
would be a first run that failed on the train.

Everything else humanize offers is in that repository, fetched when somebody asks for it: a
flow is content, and content that can change without a release is content that keeps up.

Which of the two places a flow of humanize's is kept in is humanize's own business, and is not
something anybody running one has to know. Both are offered under `official`, and a flow moved
from here to there goes on answering to the name it always had.

A directory of flows and nothing else, one directory apiece: the `__init__.py` that is the
flow, whatever it imports beside it, and the `skills/` it brings. A flowverse that is fetched
keeps its flows in a `flows/` directory, having a repository around them to keep out of the
way; these have none, being in the package, and are read where they stand.
"""
