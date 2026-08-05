# Whether a run here is profiled as well as traced, which is a thing about this directory.
#
# Nothing runs: the switch is written down, and what it does is done by the next flow that
# runs here. The programs in the trace beside it were invented by stage.py.

Output "/out/profiling.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 500
Set Padding 12
Set Framerate 10
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /Say what to do/
Show

Sleep 400ms

Type "/settings" Enter
Wait+Screen /Settings/
Sleep 2s

# Two pages: what is true of this machine, and what is remembered about this directory.
Tab
Wait+Screen /profile/
Sleep 1400ms
Screenshot "/out/profiling.png"
Sleep 400ms
