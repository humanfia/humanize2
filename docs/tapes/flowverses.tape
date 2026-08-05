# `/flowverses`: the places flows come from, and what one of them holds.
#
# Nothing is fetched here. The two that are always listed are the package's own flows and
# humanize's repository of the rest; asking what one holds reads the flows already on this
# container's disk, and no turn is taken.

Output "/out/flowverses.gif"

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

# Every place there is, whether or not it has been fetched, and where each came from.
Type "/flowverses" Enter
Wait+Screen /Flowverses/
Sleep 1400ms
Screenshot "/out/flowverses.png"
Sleep 400ms

# Enter says what one holds -- which means reading its flows, so it is asked of the one
# that was opened rather than of all of them.
Enter
Wait+Screen /What this flowverse holds/
Sleep 1400ms
Screenshot "/out/flowverse-holds.png"
Sleep 400ms
