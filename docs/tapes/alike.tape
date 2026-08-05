# One account, every backend that could be run as it.
#
# A vendor's credential is the vendor's rather than the CLI's, so an account made for one is
# often an account several others could be run as. The key typed here is the words
# `not-a-real-key`, the way in is one that runs nothing, and nothing signs in to anything.

Output "/out/alike.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 620
Set Padding 12
Set Framerate 10
Set TypingSpeed 35ms

Hide
Type "cd /work/demo && clear" Enter
Show

# Off camera, because it is the walk rather than the thing: the prompt, `/providers`, `a`,
# which CLI, and `key` -- which is a variable rather than a login, so it asks and runs
# nothing. The stills below are of each step all the same.
Hide
Type "hmz" Enter
Wait+Screen /Say what to do/
Type "/providers" Enter
Wait+Screen /Providers/
Type "a"
Wait+Screen /which coding agent/
Enter
Wait+Screen /Select how to sign in/
Down 2
Enter
Wait+Screen /API key/
Show
Sleep 1200ms
# What it is called, and the key -- which is the words `not-a-real-key`, and is drawn as
# bullets whatever it is. Typed off camera all the same: a key being typed is not a thing to
# film, and this is what a demo of one looks like.
Hide
Type "shared"
Down
Type "not-a-real-key"
Show
Sleep 800ms
Enter

# And then the question this is about: an Anthropic key is an Anthropic key whoever holds
# it, so the backends that could be run as this account are offered a copy of it.
Wait+Screen /runs more than/
Sleep 2s
Screenshot "/out/alike.png"
Sleep 400ms

# The ones this machine has installed start on; the rest are a keypress away.
Right
Sleep 700ms
Down
Sleep 400ms
Right
Sleep 1200ms
Enter

# And they are accounts of their own from here on, under the same name.
Wait+Screen /and runs/
Sleep 2s
Screenshot "/out/alike-copied.png"
Sleep 400ms
