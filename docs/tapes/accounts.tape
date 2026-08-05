# `/providers`: what there is to do with one account, and where a CLI of your own goes.
#
# The account this walks over was made by `stage.py` at a reserved-invalid endpoint with the
# words `not-a-real-token`. Nothing here signs in to anything, and no value is ever drawn.

Output "/out/accounts.gif"

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

# Every account there is, under a heading per CLI. The names of the variables each sets,
# and never a value: this is drawn where somebody can read it.
Type "/providers" Enter
Wait+Screen /Providers/
Sleep 1400ms

# Enter opens what there is to do with the one under the cursor -- four questions about one
# account, rather than four letters to read off the bottom of the screen.
Enter
Wait+Screen /What to do with this account/
Sleep 1400ms
Screenshot "/out/account-does.png"
Sleep 400ms

Escape
Sleep 700ms

# And `a` asks which CLI a new account is for -- which is also where a CLI of your own that
# speaks ACP is written down, since that is the question it answers.
Type "a"
Wait+Screen /which coding agent/
Sleep 1400ms
Screenshot "/out/account-backends.png"
Sleep 400ms
