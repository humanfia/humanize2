# `/epics`: the runs of this directory, and going into one of them.
#
# The runs were invented by stage.py -- two of them, of two flows, one of which says it can
# be picked up. Exporting reads only what is already on this container's disk, gathering the
# run's trace on its way in, and no turn is taken: the stand-in backends run nothing.

Output "/out/epics.gif"

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
# The keys under the prompt, which is the last thing drawn once the interface is up. The
# other tapes still wait on a placeholder the editor no longer draws.
Wait+Screen /ctrl\+c exit/
Show

Sleep 400ms

# Every run of a flow here, newest first: what it was, how it went, how much it opened.
Type "/epics" Enter
Wait+Screen /Epics/
Sleep 1400ms
Screenshot "/out/epics.png"
Sleep 400ms

# Enter goes into the one under the cursor: where it is written down, and what there is to
# do with it. What there is depends on the run: a flow that says it can be picked up is one
# to carry on.
Enter
Wait+Screen /resume this run/
Sleep 1400ms
Screenshot "/out/epic-does.png"
Sleep 400ms

# The whole run as one archive, with a trace of its sessions -- and the programs it ran --
# gathered into it on the way.
Down
Sleep 400ms
Enter
Wait+Screen /slices/
Sleep 1400ms
