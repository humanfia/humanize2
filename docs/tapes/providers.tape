# The accounts an agent may be run as -- and that a value is never printed back.
#
# `--no-login` writes the account down without running the backend's own way in, so this
# tape signs in to nothing and holds no credential. The endpoint is a reserved-invalid
# name and the token is the words "not-a-real-token".

Output "/out/providers.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 560
Set Padding 12
Set Framerate 20
Set TypingSpeed 20ms

Hide
Type "cd /work/demo && clear" Enter
Show

Sleep 500ms
Type "hmz providers ways claude | head -12" Enter
Sleep 3500ms

Type "hmz providers add claude/example -w gateway --no-login -s ANTHROPIC_BASE_URL=https://gateway.example.invalid -s ANTHROPIC_AUTH_TOKEN=not-a-real-token" Enter
Sleep 2500ms

Type "hmz providers list" Enter
Sleep 2s

# The names of the variables it sets, never their values. A gateway of one's own is nobody
# else's to run as, so this one says no other backend could be; `alike.tape` is the account
# that several could.
Type "hmz providers show claude/example" Enter
Sleep 4s
Screenshot "/out/providers-show.png"
Sleep 600ms
