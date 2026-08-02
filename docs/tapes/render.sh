#!/bin/sh
# Renders the documentation's terminal demos.
#
#   docs/tapes/render.sh              every tape
#   docs/tapes/render.sh tui.tape     one of them
#
# Needs docker and nothing else. Each tape is recorded inside a container built from the
# Dockerfile beside this script -- a scratch home, a throwaway project, and a stand-in for
# the coding agent CLIs -- so a recording cannot pick up an account, a path or a hostname.
#
# The GIFs land in docs/public/demo/ and are committed. Nothing in CI runs this.

set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
out="$root/docs/public/demo"
image=humanize-vhs

# `check-added-large-files` refuses anything over 500 KB, and a page nobody waits for is a
# page nobody reads. This is the smaller promise the tapes are written against.
limit=460800

echo "==> building $image"
DOCKER_BUILDKIT=1 docker build --quiet -t "$image" -f "$here/Dockerfile" "$root" >/dev/null

mkdir -p "$out"

if [ "$#" -gt 0 ]; then
    tapes=$*
else
    tapes=$(cd "$here" && echo ./*.tape)
fi

for tape in $tapes; do
    name=$(basename "$tape")
    echo "==> $name"
    docker run --rm \
        -v "$here:/tapes:ro" \
        -v "$out:/out" \
        "$image" "/tapes/$name"
done

# The container writes as root. Hand what it wrote back, so the tree is not half root's.
docker run --rm -v "$out:/out" --entrypoint chown "$image" \
    -R "$(id -u):$(id -g)" /out

echo
failed=0
for gif in "$out"/*.gif; do
    [ -e "$gif" ] || continue
    size=$(wc -c < "$gif")
    printf '%-28s %6s KB\n' "$(basename "$gif")" "$((size / 1024))"
    if [ "$size" -gt "$limit" ]; then
        echo "    too large: shorten the tape, or drop Width/Height/Framerate" >&2
        failed=1
    fi
done

echo
echo "Look at what you rendered before committing it. A demo must show humanize and"
echo "nothing about the machine it was recorded on."

exit "$failed"
