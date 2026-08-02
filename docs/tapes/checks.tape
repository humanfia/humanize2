# Everything knowable before the first turn is checked before the first turn.
#
# No agent runs in this tape. Each line below is refused by `hmz exec` itself.

Output "/out/checks.gif"

Set Shell "bash"
Set FontSize 16
Set Width 1000
Set Height 620
Set Padding 12
Set Framerate 20
Set TypingSpeed 30ms

Hide
Type "cd /work/demo && clear" Enter
Show

Sleep 500ms
Type "cat .humanize/flows/twice.py" Enter
Sleep 3s

Type `hmz exec -f twice -a claude:high "fix the build"` Enter
Sleep 2500ms

Type `hmz exec -f twice -a claude/claude-opus-4-8:high -a codex/gpt-5.6-sol:high "fix the build"` Enter
Sleep 3s

Type `hmz exec -f nosuchflow -a claude/claude-opus-4-8:high "fix the build"` Enter
Sleep 3s
