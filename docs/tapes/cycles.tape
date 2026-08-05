# `/cycles`: the runs of this directory, and what there is to do with one.
#
# The runs were invented by stage.py -- two of them, of two flows, one of which says it can
# be picked up. Collecting a trace reads only what is already on this container's disk, and
# no turn is taken: the stand-in backends run nothing.

Output "/out/cycles.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 560
Set Padding 12
Set Framerate 10
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /Say what to do/
Show

Sleep 400ms

# Every run of a flow here, newest first: what it was, how it went, how much it opened.
Type "/cycles" Enter
Wait+Screen /Cycles/
Sleep 1400ms
Screenshot "/out/cycles.png"
Sleep 400ms

# Enter says what there is to do with the one under the cursor. What there is depends on
# the run: a flow that says it can be picked up is one to carry on.
Enter
Wait+Screen /What to do with this run/
Sleep 1400ms
Screenshot "/out/cycle-does.png"
Sleep 400ms

# Its sessions, and the programs it ran, gathered into one trace -- written beside the run.
Down
Sleep 400ms
Enter
Wait+Screen /slices/
Sleep 1400ms
