# The terminal interface: the box it opens with, the commands, and the flow picker.
#
# No turn is taken. The backends here are stand-ins that run nothing, and the tape leaves
# before anything could be said to one.

Output "/out/tui.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 620
Set Padding 12
Set Framerate 20
Set TypingSpeed 50ms

Hide
Type "cd /work/demo && clear" Enter
Show

Sleep 500ms
Type "hmz" Enter
Sleep 4s

# Type `/` and what the line could be is listed under the editor, a line about each.
Type "/"
Sleep 3s

Backspace
Sleep 500ms

# The flows there are, a tab per place they come from.
Type "/flow"
Sleep 1500ms
Enter
Sleep 700ms
Enter
Sleep 3s

Right
Sleep 2500ms

Escape
Sleep 1500ms

# Two ctrl+c leave, whatever was going on.
Ctrl+C
Ctrl+C
Sleep 1500ms
