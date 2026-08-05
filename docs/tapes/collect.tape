# What a run leaves behind, gathered into one Chrome trace.
#
# The runs and the transcripts this reads were invented by stage.py. No agent ran, here or
# anywhere: collecting reads what is already on this container's disk.

Output "/out/collect.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 500
Set Padding 12
Set Framerate 20
Set TypingSpeed 25ms

Hide
Type "cd /work/demo && clear" Enter
Show

Sleep 500ms
# The last run of this directory, its sessions and the programs it ran, into the run's own
# directory -- which already holds what happened and where each session was logged.
Type "hmz trace collect" Enter
Sleep 3500ms
Screenshot "/out/collect.png"
Sleep 600ms

# Or one run by name, wherever it comes among them.
Type "hmz trace collect --cycle 20260720T1000" Enter
Sleep 3500ms

# And a trace is also a thing to attach to an issue.
Type "hmz trace collect --output /tmp/for-the-issue.json" Enter
Sleep 3s
