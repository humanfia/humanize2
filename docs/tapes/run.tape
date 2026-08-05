# What one run leaves behind: a directory, and everything the run was.
#
# The runs were invented by stage.py, sessions and all -- written down by the code that
# writes down a real one. Nothing here starts a backend.

Output "/out/run.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 500
Set Padding 12
Set Framerate 15
Set TypingSpeed 25ms

Hide
Type "cd /work/demo && clear" Enter
Type "run=$(ls -d /root/.humanize/cycles/-work-demo/*/ | tail -1)" Enter
Type "clear" Enter
Show

Sleep 500ms
# One run of one flow is one directory: what happened, what the flow left behind, the
# programs it ran, and a link to every conversation it opened.
Type 'ls "$run"' Enter
Sleep 2200ms
Screenshot "/out/run.png"
Sleep 600ms

# A session is named for whose it was, what took its turns and which account they ran as.
Type 'ls "$run"sessions' Enter
Sleep 2800ms

# And the name points at the log the backend itself wrote, which humanize reads and writes
# where the backend keeps it: the link is for whoever is reading the run afterwards.
Type 'ls -l "$run"sessions/*/ | tail -1' Enter
Sleep 3s
Screenshot "/out/run-linked.png"
Sleep 600ms

# What a flow that says it can be picked up left for the next run of it.
Type 'cat "$run"state.json' Enter
Sleep 2800ms
