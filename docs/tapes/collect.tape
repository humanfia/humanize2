# What a run leaves behind, gathered into one Chrome trace.
#
# The transcript this reads was invented by stage.py. No agent ran, here or anywhere.

Output "/out/collect.gif"

Set Shell "bash"
Set FontSize 16
Set Width 1000
Set Height 500
Set Padding 12
Set Framerate 20
Set TypingSpeed 30ms

Hide
Type "cd /work/demo && clear" Enter
Show

Sleep 500ms
Type "hmz trace collect" Enter
Sleep 3s

Type "ls .humanize" Enter
Sleep 2s

Type "hmz trace collect --start '1 minute ago'" Enter
Sleep 3s
