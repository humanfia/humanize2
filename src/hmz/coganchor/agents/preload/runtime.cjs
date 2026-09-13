// The preload layer, as the runtime sees it: the Node process a coding agent CLI is running
// on, patched from inside so that what its turn actually does -- the processes it starts, the
// files it reads and writes, the connections it opens -- is said out loud to humanize.
//
// CommonJS because `--require` takes CommonJS, and it is `--require` that puts this here:
// `NODE_OPTIONS="--require <this file>"` is read by Node before the CLI's own entry point, so
// every patch below is in place before the CLI has run a line. Which is also the whole of its
// reach -- a CLI shipped as a compiled binary has no Node to load this into, and
// `hmz.coganchor.backends` is where it is written down which of them do.
//
// Three rules govern everything here, and each of them is the reason for code that would
// otherwise read as overcautious:
//
//  1. Fail open. This file runs inside somebody else's program. A preload that throws takes
//     the agent down with it, so every patch, every report and the whole of the start-up is
//     wrapped: what cannot be observed is not observed, and the turn goes on exactly as it
//     would have gone on without any of this.
//  2. Never hold the process up. The socket is unrefed, so a connection nobody is reading is
//     never what keeps a CLI alive past its work, and nothing here waits on anything: a report
//     is one non-blocking write, and one that will not go is dropped rather than waited on.
//  3. This CLI and no other program. `NODE_OPTIONS` is inherited by every process the CLI
//     spawns, and what is wanted is neither end of that. Every Node program under a turn --
//     a package manager, a language server, a script the agent wrote -- reporting its own
//     reads as the agent's work is noise, and the agent running it was already reported here
//     by the spawn that ran it. But a CLI that re-execs itself is still the CLI: qwen's entry
//     point starts a second `node` on the bundle beside it and does the whole turn there, so
//     a layer that stopped at the first process would watch a launcher. So the rule is the
//     program rather than the process: the install directory the first process was started
//     from is passed down, and a process whose own program is not under it strips the
//     variables, reports nothing, and hands nothing on to anything it runs in turn.
"use strict";

// Where to report, as `hmz.coganchor.agents.preload` names the socket it is listening on. Unset means
// there is nobody to report to, which is how any other Node program on this machine loads this
// file -- a child that kept it, a `node` somebody ran by hand -- and does nothing at all.
const AT = "HMZ_PRELOAD_AT";

// The variable this file arrived through, which is trimmed back to whatever else was in it by
// any process that is not the program the layer was put here for.
const OPTIONS = "NODE_OPTIONS";

// Which program the layer was put here for, written by the first process to load it so that
// the ones it starts can tell whether they are still that program. A process with nothing to
// name itself by -- `node -e`, a REPL -- says so with this, which nothing else answers to.
const IN = "HMZ_PRELOAD_IN";
const NOBODY = "-";

// How far up from a script its own package is looked for. Deep enough for the layouts these
// CLIs ship in -- an entry point in `bin/` or `dist/` of its package, under a `node_modules`
// -- and shallow enough that a script with no package around it stops looking.
const LEVELS = 6;

// What a write that did not go says when it is worth trying again later: the reader is behind,
// or the connection is not up yet. Anything else is a socket nothing more is written to. A
// connection that never comes up says so on the socket itself, which is what stops this.
const AGAIN = ["EAGAIN", "EWOULDBLOCK", "ENOTCONN", "EINTR"];

// How many things one process may say before it goes quiet, and how long any one of them may
// be. A driven turn says a couple of thousand things -- a CLI reads its own state, its
// settings and the project, and each of those is a line here -- so the ceiling is high enough
// that no ordinary session reaches it and low enough that a runaway one is bounded. Going
// quiet is said out loud, so that a gap in what was observed reads as a gap rather than as a
// turn that did nothing.
const LIMIT = 100000;
const LONGEST = 4096;

function start() {
  const at = process.env[AT];
  if (!at) {
    return;
  }
  const net = require("node:net");
  // Captured before anything below is patched, so that the one connection this file makes is
  // not a connection this file reports -- which would be a report that makes another report.
  const connecting = net.Socket.prototype.connect;

  const fs = require("node:fs");
  const path = require("node:path");
  // Whether this process is still the program the layer was put here for. The first one says
  // which program that is; anything started under it that is some other program watches
  // nothing and passes nothing on.
  const held = belongs(fs, path, running(fs));
  const me = held.name || held.root;
  const whom = process.env[IN];
  if (whom === undefined) {
    process.env[IN] = me || NOBODY;
  } else if (!me || me !== whom) {
    mine();
    return;
  }
  // Where this program's own files are, which are the ones not worth reporting: a bundle
  // loading itself is not a turn doing anything, and there are thousands of those before a CLI
  // has read a word of the prompt. Only where a package says where it begins -- a script with
  // none around it has no install to speak of, and the directory it happens to sit in is as
  // likely to be the work as the program.
  const install = held.name ? held.root : "";

  // Captured before anything below is patched, for the reason `connecting` is: what this file
  // writes its own reports with must not be a thing this file reports.
  const writing = fs.writeSync;

  let carrying = new net.Socket();
  let said = 0;
  let telling = false;
  let inside = 0;
  // How much went unsaid because the reader was behind. Said as a number the next time
  // anything gets through: a gap has to read as a gap, and what was in it is gone.
  let dropped = 0;

  // Nowhere to report to is not a failure: humanize may have stopped listening, or may never
  // have been there. The socket is dropped and the turn goes on, saying nothing.
  carrying.on("error", () => {
    carrying = null;
  });
  connecting.call(carrying, at);
  // Never what keeps this process alive: a CLI whose work is done must exit whether or not
  // anybody is still reading what it said.
  carrying.unref();
  // The descriptor under the socket, which is what every report is actually written to. A
  // queued write is a write that happens when the event loop next runs, and a CLI that takes
  // its turn and exits -- `process.exit` in a `--version`, in a turn that failed, in most of a
  // command-per-turn backend's life -- exits with everything it saw still queued. Writing to
  // the descriptor is writing now. None on a platform whose sockets have no descriptor to
  // name, where the queue is all there is and a short-lived process says less.
  const fd =
    carrying._handle && typeof carrying._handle.fd === "number" && carrying._handle.fd >= 0
      ? carrying._handle.fd
      : null;

  function report(did, what) {
    if (carrying === null || telling || said >= LIMIT) {
      return;
    }
    // A report is written to a socket, and a socket is one of the things patched below.
    // Without this, saying that something connected would itself be something connecting.
    telling = true;
    try {
      // Said before the report it is about, and only counted as said once it has gone: a
      // count reset on a line that did not go is a gap nobody is ever told about.
      if (dropped > 0) {
        const behind = dropped + " dropped while the reader was behind";
        if (writes({ did: "quiet", what: behind })) {
          dropped = 0;
        }
      }
      if (writes({ did: did, what: String(what).slice(0, LONGEST) })) {
        said += 1;
        if (said === LIMIT) {
          writes({ did: "quiet", what: LIMIT + " said; the rest of this process is not" });
        }
      }
    } finally {
      telling = false;
    }
  }

  // One report, written now. The descriptor libuv made is a non-blocking one, so a reader that
  // has fallen behind makes this throw rather than makes this wait -- which is the whole of the
  // backpressure this layer may have: what cannot be written is dropped, because holding a turn
  // up to say what it did is worse than not saying it.
  function writes(what) {
    try {
      const line = JSON.stringify(what) + "\n";
      if (fd === null) {
        carrying.write(line);
      } else {
        // A short write loses its own line and garbles the next; both are unreadable, and the
        // reader drops what it cannot read. Nothing else in the stream is affected.
        writing(fd, line);
      }
      return true;
    } catch (trouble) {
      if (trouble && AGAIN.indexOf(trouble.code) >= 0) {
        dropped += 1;
        return false;
      }
      // A socket that will not take a line is one nothing more is written to.
      carrying = null;
      return false;
    }
  }

  function watch(of, name, did, about) {
    const was = of[name];
    if (typeof was !== "function") {
      return; // a runtime without it is a runtime with nothing here to patch
    }
    const patched = function (...args) {
      // Only the outermost call: `exec` reaches for `execFile`, which reaches for `spawn`, and
      // one command the agent ran is one thing to say rather than three.
      if (inside === 0) {
        try {
          const what = about(args);
          if (what !== null) {
            report(did, what);
          }
        } catch {
          // A report that could not be made is not a call that could not be made.
        }
      }
      inside += 1;
      try {
        return was.apply(this, args);
      } finally {
        inside -= 1;
      }
    };
    // Whatever else hung off the call hangs off the patch, down to the name and the arity.
    // `util.promisify` reads a symbol off `exec` and `execFile` saying what their promised form
    // answers with -- `{ stdout, stderr }` rather than the first thing the callback was given --
    // so a patch that dropped it would quietly change what `await exec(...)` comes back as.
    for (const key of Reflect.ownKeys(was)) {
      try {
        Object.defineProperty(patched, key, Object.getOwnPropertyDescriptor(was, key));
      } catch {
        // A property that will not be redefined is one the original keeps to itself.
      }
    }
    of[name] = patched;
  }

  // What was run, as a command line: the program and what it was given, which is what a person
  // reading a turn's work wants to see and is what every one of these takes first.
  function commanded(args) {
    const program = String(args[0] === undefined ? "" : args[0]);
    const rest = Array.isArray(args[1]) ? args[1] : [];
    return rest.length ? program + " " + rest.join(" ") : program;
  }

  // Which file, for the calls that take one. A descriptor says nothing about which file it is
  // -- whatever opened it is where that was known -- so a call on one is passed through unsaid,
  // and so is anything that is the CLI reading or writing its own install.
  function pathed(args) {
    const named = args[0];
    if (named === null || named === undefined || typeof named === "number") {
      return null;
    }
    const where = String(named.pathname === undefined ? named : named.pathname);
    return install && where.startsWith(install + path.sep) ? null : where;
  }

  // Where a connection went, in every shape `connect` takes it: an options object, a port with
  // a host beside it, or the path of a socket -- and the pair of those and a callback that
  // `net.connect` normalizes its arguments into before handing them here, which is the shape
  // every connection a program makes through the module rather than through a socket arrives
  // in.
  function reached(args) {
    const first = Array.isArray(args[0]) ? args[0][0] : args[0];
    if (first !== null && typeof first === "object") {
      if (first.path) {
        return String(first.path);
      }
      return (first.host === undefined ? "localhost" : first.host) + ":" + first.port;
    }
    if (typeof first === "number") {
      return (typeof args[1] === "string" ? args[1] : "localhost") + ":" + first;
    }
    return String(first);
  }

  // The processes. Each entry point rather than `spawn` alone: the ones that reach for another
  // do it through their own binding rather than through the export patched here, so a patch on
  // `spawn` would see every `spawn` and miss every `exec`.
  const child = require("node:child_process");
  const spawning = ["spawn", "spawnSync", "exec", "execSync", "execFile", "execFileSync", "fork"];
  for (const name of spawning) {
    watch(child, name, "spawn", commanded);
  }

  // The files. These and not every entry point `fs` has: a patch per entry point is a patch to
  // carry per release, and what a coding agent's own tools read and write a file through is
  // this handful, in whichever of its spellings the CLI was written against. The promises are
  // the same object `node:fs/promises` exports, so both of those are patched at once.
  for (const name of ["readFile", "readFileSync"]) {
    watch(fs, name, "read", pathed);
  }
  for (const name of ["writeFile", "writeFileSync", "appendFile", "appendFileSync"]) {
    watch(fs, name, "write", pathed);
  }
  const promised = fs.promises;
  if (promised) {
    watch(promised, "readFile", "read", pathed);
    for (const name of ["writeFile", "appendFile"]) {
      watch(promised, name, "write", pathed);
    }
  }

  // The wire. One patch rather than one per module: `http`, `https`, `tls` and whatever the CLI
  // fetches with all end at a socket connecting, so this is the one place they pass through.
  watch(net.Socket.prototype, "connect", "connect", reached);
}

// Which script this process is actually running, resolved: a CLI is installed as a link into
// its own package, and what it re-execs itself as is named inside that package rather than
// through the link. "" for a process with no script to name, and for one whose script cannot be
// resolved -- neither of which is a CLI being driven.
function running(fs) {
  try {
    const file = process.argv[1];
    return file ? fs.realpathSync(file) : "";
  } catch {
    return "";
  }
}

// Which program that script belongs to, and where that program's own files are: the name of
// the nearest package around it, and that package's directory.
//
// The name rather than the path, because a CLI re-execs itself to wherever its own updater put
// its newest copy -- qwen's entry point starts the managed install under the user's home in
// preference to the one beside it -- and a rule written in paths would call that second process
// somebody else's program and stop watching the half of the turn that does the work. Two copies
// of one CLI are one program; a package manager the agent runs is another, whatever directory
// it happens to be under.
//
// The directory for the other half of it: the CLI reading and writing its own install is the
// program loading itself rather than the turn doing anything, and there are thousands of those
// before a word of the prompt has been read.
function belongs(fs, path, file) {
  const held = { name: "", root: file ? path.dirname(file) : "" };
  let at = held.root;
  for (let up = 0; at && up < LEVELS; up += 1) {
    try {
      const said = JSON.parse(fs.readFileSync(path.join(at, "package.json"), "utf8"));
      if (said && typeof said.name === "string" && said.name) {
        return { name: said.name, root: at };
      }
    } catch {
      // No manifest here, or one nothing can read: keep looking further up.
    }
    const over = path.dirname(at);
    if (over === at) {
      break;
    }
    at = over;
  }
  return held;
}

// Somebody else's program, which this layer is not about. The `--require` is taken back out of
// `NODE_OPTIONS` -- that one and nothing else, so a `--max-old-space-size` somebody set stays
// exactly as they set it -- and the two variables of ours go with it, so that whatever this
// program runs in turn finds nothing here at all.
function mine() {
  const held = process.env[OPTIONS] || "";
  const left = held
    .replace('--require "' + __filename + '"', "")
    .replace("--require " + __filename, "")
    .trim();
  if (left) {
    process.env[OPTIONS] = left;
  } else {
    delete process.env[OPTIONS];
  }
  delete process.env[AT];
  delete process.env[IN];
}

try {
  start();
} catch {
  // Fail open, and say nothing: this file is a way of watching a turn, and a turn that will
  // not run because something was watching it is worse than a turn nobody watched.
}
