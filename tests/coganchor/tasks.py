"""The smoke-task catalogue.

Each task is a small, deterministic piece of work an agent might do.  They run
through the real interception path -- seccomp filter, ptrace supervisor, shadow
tree, remote exec -- and are checked from *the target's* directory, so a task
only passes if its effects genuinely landed on the target.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SMOKE_TASKS", "SmokeTask"]


@dataclass(frozen=True, slots=True)
class SmokeTask:
    """One end-to-end scenario.

    ``runner`` decides which interception path is under test.  A ``bash`` task
    exercises remote execution, because every command the shell runs is
    forwarded.  A ``python`` task exercises the *local* path instead: the
    interpreter is the agent, so its ``mkdir``, ``rename`` and ``unlink``
    syscalls are trapped and replayed rather than executed somewhere else --
    exactly what a coding agent's file-editing tools do.
    """

    name: str
    script: str
    runner: str = "bash"
    #: Files placed on the target before the agent runs.  They exist nowhere
    #: else, so reading them proves the data crossed the connection.
    seed: dict[str, str] = field(default_factory=dict)
    #: Substrings the agent's output must contain.
    stdout: tuple[str, ...] = ()
    #: Substrings the agent's output must not contain.
    absent: tuple[str, ...] = ()
    exit_code: int = 0
    #: Exact file contents expected on the target afterwards.
    target_files: dict[str, str] = field(default_factory=dict)
    #: Paths that must not exist on the target afterwards.
    target_missing: tuple[str, ...] = ()
    stdin: bytes = b""

    @property
    def command(self) -> tuple[str, ...]:
        runner = "bash" if self.runner == "bash" else "python3"
        return (runner, "-c", self.script)


_LINES = "alpha\nbeta\ngamma\ndelta\n"
_WORDS = "pear\napple\npear\nfig\napple\npear\n"

SMOKE_TASKS: tuple[SmokeTask, ...] = (
    # ---------------------------------------------------------------- reading
    SmokeTask(
        name="read_file",
        seed={"notes.txt": "the secret is halibut\n"},
        script="cat notes.txt",
        stdout=("the secret is halibut",),
    ),
    SmokeTask(
        name="read_nested_file",
        seed={"src/lib/util.py": "def helper():\n    return 41 + 1\n"},
        script="cat src/lib/util.py",
        stdout=("return 41 + 1",),
    ),
    SmokeTask(
        name="read_head_and_tail",
        seed={"lines.txt": _LINES},
        script="head -1 lines.txt; tail -1 lines.txt",
        stdout=("alpha", "delta"),
    ),
    SmokeTask(
        name="count_lines",
        seed={"lines.txt": _LINES},
        script="wc -l < lines.txt",
        stdout=("4",),
    ),
    SmokeTask(
        name="list_directory",
        seed={"a.txt": "a\n", "b.txt": "b\n", "sub/c.txt": "c\n"},
        script="ls | sort | tr '\\n' ' '",
        stdout=("a.txt b.txt sub",),
    ),
    SmokeTask(
        name="find_recursive",
        seed={"x/1.txt": "1\n", "x/y/2.txt": "2\n", "z.txt": "3\n"},
        script="find . -type f | sort | tr '\\n' ' '",
        stdout=("./x/1.txt ./x/y/2.txt ./z.txt",),
    ),
    SmokeTask(
        name="shell_glob",
        seed={"one.txt": "1\n", "two.txt": "2\n", "three.md": "3\n"},
        script="echo *.txt",
        stdout=("one.txt two.txt",),
        absent=("three.md",),
    ),
    SmokeTask(
        name="grep_in_file",
        seed={"haystack.txt": "nope\nfound the needle here\nnope\n"},
        script="grep -n needle haystack.txt",
        stdout=("2:found the needle here",),
    ),
    SmokeTask(
        name="grep_recursive",
        seed={"a/one.py": "# needle\n", "b/two.py": "# other\n"},
        script="grep -rl needle . | sort",
        stdout=("./a/one.py",),
        absent=("two.py",),
    ),
    SmokeTask(
        name="stat_reports_target_size",
        seed={"sized.txt": "0123456789"},
        script="stat -c %s sized.txt",
        stdout=("10",),
    ),
    SmokeTask(
        name="test_file_exists",
        seed={"present.txt": "yes\n"},
        script="test -f present.txt && echo exists; test -f absent.txt || echo missing",
        stdout=("exists", "missing"),
    ),
    SmokeTask(
        name="read_empty_file",
        seed={"empty.txt": ""},
        script="wc -c < empty.txt",
        stdout=("0",),
    ),
    SmokeTask(
        name="read_large_file",
        seed={"large.txt": "x" * 300_000},
        script="wc -c < large.txt",
        stdout=("300000",),
    ),
    SmokeTask(
        name="read_unicode_filename",
        seed={"ünïcode-ファイル.txt": "héllo → wörld\n"},
        script="cat ünïcode-ファイル.txt",
        stdout=("héllo → wörld",),
    ),
    SmokeTask(
        name="read_filename_with_spaces",
        seed={"with space.txt": "spaced out\n"},
        script='cat "with space.txt"',
        stdout=("spaced out",),
    ),
    SmokeTask(
        name="read_hidden_file",
        seed={".hidden": "concealed\n"},
        script="cat .hidden; ls -a | grep -c '^\\.hidden$'",
        stdout=("concealed", "1"),
    ),
    SmokeTask(
        name="concatenate_files",
        seed={"first.txt": "one\n", "second.txt": "two\n"},
        script="cat first.txt second.txt",
        stdout=("one", "two"),
    ),
    SmokeTask(
        name="sort_and_count",
        seed={"words.txt": _WORDS},
        script="sort words.txt | uniq -c | sort -rn | head -1 | tr -s ' '",
        stdout=("3 pear",),
    ),
    SmokeTask(
        name="awk_field_extraction",
        seed={"table.tsv": "id\tname\n1\talpha\n2\tbeta\n"},
        script="awk -F'\\t' 'NR>1 {print $2}' table.tsv | tr '\\n' ','",
        stdout=("alpha,beta,",),
    ),
    SmokeTask(
        name="read_deeply_nested",
        seed={"a/b/c/d/e/f/g/deep.txt": "bottom\n"},
        script="cat a/b/c/d/e/f/g/deep.txt",
        stdout=("bottom",),
    ),
    # ---------------------------------------------------------------- writing
    SmokeTask(
        name="write_via_redirect",
        script="echo written > out.txt",
        target_files={"out.txt": "written\n"},
    ),
    SmokeTask(
        name="append_to_file",
        script="echo one > log.txt; echo two >> log.txt",
        target_files={"log.txt": "one\ntwo\n"},
    ),
    SmokeTask(
        name="write_via_tee",
        script="echo teed | tee copy.txt",
        stdout=("teed",),
        target_files={"copy.txt": "teed\n"},
    ),
    SmokeTask(
        name="write_from_python",
        script="python3 -c \"open('py.txt','w').write('from python')\"",
        target_files={"py.txt": "from python"},
    ),
    SmokeTask(
        name="edit_in_place_with_sed",
        seed={"config.ini": "mode = old\nkeep = yes\n"},
        script="sed -i 's/old/new/' config.ini; cat config.ini",
        stdout=("mode = new",),
        target_files={"config.ini": "mode = new\nkeep = yes\n"},
    ),
    SmokeTask(
        name="touch_creates_file",
        script="touch fresh.txt && test -f fresh.txt && echo created",
        stdout=("created",),
        target_files={"fresh.txt": ""},
    ),
    SmokeTask(
        name="make_directory",
        script="mkdir plain && test -d plain && echo made",
        stdout=("made",),
    ),
    SmokeTask(
        name="make_nested_directories",
        script="mkdir -p deep/a/b/c && echo leaf > deep/a/b/c/f.txt",
        target_files={"deep/a/b/c/f.txt": "leaf\n"},
    ),
    SmokeTask(
        name="copy_file",
        seed={"source.txt": "duplicate me\n"},
        script="cp source.txt copy.txt",
        target_files={"copy.txt": "duplicate me\n", "source.txt": "duplicate me\n"},
    ),
    SmokeTask(
        name="rename_file",
        seed={"before.txt": "same content\n"},
        script="mv before.txt after.txt",
        target_files={"after.txt": "same content\n"},
        target_missing=("before.txt",),
    ),
    SmokeTask(
        name="move_into_directory",
        seed={"item.txt": "moved\n"},
        script="mkdir -p box && mv item.txt box/",
        target_files={"box/item.txt": "moved\n"},
        target_missing=("item.txt",),
    ),
    SmokeTask(
        name="remove_file",
        seed={"doomed.txt": "goodbye\n"},
        script="rm doomed.txt && echo removed",
        stdout=("removed",),
        target_missing=("doomed.txt",),
    ),
    SmokeTask(
        name="remove_tree",
        seed={"tree/a/b.txt": "x\n", "tree/c.txt": "y\n"},
        script="rm -rf tree && echo gone",
        stdout=("gone",),
        target_missing=("tree",),
    ),
    SmokeTask(
        name="write_unicode_content",
        script='printf "naïve café → 日本\\n" > uni.txt',
        target_files={"uni.txt": "naïve café → 日本\n"},
    ),
    SmokeTask(
        name="write_large_file",
        script="head -c 500000 /dev/zero | tr '\\0' 'q' > big.txt; wc -c < big.txt",
        stdout=("500000",),
    ),
    SmokeTask(
        name="write_binary_file",
        script="head -c 4096 /dev/urandom > blob.bin; wc -c < blob.bin",
        stdout=("4096",),
    ),
    SmokeTask(
        name="chmod_makes_executable",
        script="printf '#!/bin/sh\\necho ran\\n' > s.sh; chmod +x s.sh; ./s.sh",
        stdout=("ran",),
    ),
    SmokeTask(
        name="create_symlink",
        seed={"real.txt": "pointed at\n"},
        script="ln -s real.txt alias.txt; readlink alias.txt; cat alias.txt",
        stdout=("real.txt", "pointed at"),
    ),
    SmokeTask(
        name="create_hardlink",
        seed={"origin.txt": "shared\n"},
        script="ln origin.txt linked.txt; cat linked.txt",
        stdout=("shared",),
        target_files={"linked.txt": "shared\n"},
    ),
    SmokeTask(
        name="truncate_file",
        seed={"trim.txt": "0123456789"},
        script="truncate -s 4 trim.txt; wc -c < trim.txt",
        stdout=("4",),
        target_files={"trim.txt": "0123"},
    ),
    SmokeTask(
        name="overwrite_existing_file",
        seed={"replace.txt": "old content that is long\n"},
        script="echo new > replace.txt",
        target_files={"replace.txt": "new\n"},
    ),
    SmokeTask(
        name="read_modify_write_cycle",
        seed={"counter.txt": "1\n"},
        script="n=$(cat counter.txt); echo $((n + 41)) > counter.txt; cat counter.txt",
        stdout=("42",),
        target_files={"counter.txt": "42\n"},
    ),
    # ---------------------------------------------------------------- processes
    SmokeTask(
        name="nonzero_exit_code",
        script="exit 42",
        exit_code=42,
    ),
    SmokeTask(
        name="failed_command_status",
        script="/bin/false; echo status=$?",
        stdout=("status=1",),
    ),
    SmokeTask(
        name="stderr_is_separate",
        script="echo to-out; echo to-err >&2",
        stdout=("to-out",),
    ),
    SmokeTask(
        name="three_stage_pipeline",
        seed={"words.txt": _WORDS},
        script="cat words.txt | sort | uniq | tr '\\n' ' '",
        stdout=("apple fig pear",),
    ),
    SmokeTask(
        name="subshell_isolation",
        script="x=outer; (x=inner; echo sub=$x); echo main=$x",
        stdout=("sub=inner", "main=outer"),
    ),
    SmokeTask(
        name="background_job_and_wait",
        script="(sleep 0.1; echo late) & echo early; wait",
        stdout=("early", "late"),
    ),
    SmokeTask(
        name="environment_passthrough",
        script="MARKER=carried env | grep '^MARKER='",
        stdout=("MARKER=carried",),
    ),
    SmokeTask(
        name="arguments_with_spaces",
        script='printf "%s|" "one two" "three four"; echo',
        stdout=("one two|three four|",),
    ),
    SmokeTask(
        name="stdin_from_pipe",
        script="printf 'piped\\n' | cat",
        stdout=("piped",),
    ),
    SmokeTask(
        name="stdin_from_file",
        seed={"input.txt": "from a file\n"},
        script="cat < input.txt",
        stdout=("from a file",),
    ),
    SmokeTask(
        name="stdin_from_agent",
        script="cat",
        stdin=b"typed by the operator\n",
        stdout=("typed by the operator",),
    ),
    SmokeTask(
        name="here_document",
        script="cat <<'END'\nheredoc body\nEND",
        stdout=("heredoc body",),
    ),
    SmokeTask(
        name="command_substitution",
        seed={"name.txt": "world\n"},
        script="echo hello $(cat name.txt)",
        stdout=("hello world",),
    ),
    SmokeTask(
        name="exec_by_absolute_path",
        script="/bin/echo absolute",
        stdout=("absolute",),
    ),
    SmokeTask(
        name="exec_resolved_via_path",
        script="env printf 'resolved\\n'",
        stdout=("resolved",),
    ),
    SmokeTask(
        name="nested_shells",
        script="bash -c 'bash -c \"echo three levels deep\"'",
        stdout=("three levels deep",),
    ),
    SmokeTask(
        name="many_sequential_commands",
        script="for i in $(seq 1 20); do echo -n $i,; done; echo",
        stdout=("1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,",),
    ),
    SmokeTask(
        name="loop_creating_many_files",
        script="for i in $(seq 1 50); do echo $i > f$i.txt; done; ls f*.txt | wc -l",
        stdout=("50",),
        target_files={"f7.txt": "7\n", "f50.txt": "50\n"},
    ),
    SmokeTask(
        name="signal_exit_status",
        script="bash -c 'kill -TERM $$' ; echo status=$?",
        stdout=("status=143",),
    ),
    # ------------------------------------------------------------- toolchains
    SmokeTask(
        name="run_python_script_file",
        seed={
            "script.py": "import os\nprint('cwd-has', len(os.listdir('.')), 'entries')\n"
        },
        script="python3 script.py",
        stdout=("cwd-has 1 entries",),
    ),
    SmokeTask(
        name="python_reads_and_writes",
        seed={"data.json": '{"value": 21}\n'},
        script=(
            'python3 -c "'
            "import json;"
            "d=json.load(open('data.json'));"
            "d['value']*=2;"
            "json.dump(d, open('data.json','w'))\"; cat data.json"
        ),
        stdout=('"value": 42',),
    ),
    SmokeTask(
        name="git_init_add_commit",
        script=(
            "git init -q . && git config user.email a@b && git config user.name tester && "
            "echo tracked > file.txt && git add file.txt && "
            "git -c commit.gpgsign=false commit -qm 'initial' && git log --oneline | wc -l"
        ),
        stdout=("1",),
        target_files={"file.txt": "tracked\n"},
    ),
    SmokeTask(
        name="git_sees_agent_edit",
        script=(
            "git init -q . && git config user.email a@b && git config user.name tester && "
            "echo v1 > tracked.txt && git add . && "
            "git -c commit.gpgsign=false commit -qm one && "
            "echo v2 > tracked.txt && git status --porcelain"
        ),
        stdout=("M tracked.txt",),
        target_files={"tracked.txt": "v2\n"},
    ),
    SmokeTask(
        name="shell_loop_over_files",
        seed={"a.txt": "1\n", "b.txt": "2\n", "c.txt": "3\n"},
        script="for f in *.txt; do echo -n \"$f=$(cat $f | tr -d '\\n') \"; done; echo",
        stdout=("a.txt=1 b.txt=2 c.txt=3",),
    ),
    # ------------------------------------------------------------------ edges
    SmokeTask(
        name="remote_write_then_agent_read",
        script=(
            "python3 -c \"open('made-remotely.txt','w')"
            ".write('by the target')\"; cat made-remotely.txt"
        ),
        stdout=("by the target",),
        target_files={"made-remotely.txt": "by the target"},
    ),
    SmokeTask(
        name="agent_write_then_remote_read",
        script="echo 'written locally' > handoff.txt; grep -c locally handoff.txt",
        stdout=("1",),
        target_files={"handoff.txt": "written locally\n"},
    ),
    SmokeTask(
        name="interleaved_reads_and_writes",
        seed={"seed.txt": "start\n"},
        script=(
            "cat seed.txt > step1.txt && echo more >> step1.txt && "
            "sort step1.txt > step2.txt && cat step2.txt | tr '\\n' '/'"
        ),
        stdout=("more/start/",),
        target_files={"step2.txt": "more\nstart\n"},
    ),
    SmokeTask(
        name="local_paths_still_resolve",
        script="test -r /etc/hostname && echo local-readable",
        stdout=("local-readable",),
    ),
    SmokeTask(
        name="missing_file_gives_enoent",
        script="cat no-such-file.txt 2>&1; echo status=$?",
        stdout=("No such file", "status=1"),
    ),
    SmokeTask(
        name="permission_error_propagates",
        seed={"locked.txt": "secret\n"},
        script="chmod 000 locked.txt; cat locked.txt 2>&1 | tail -1; chmod 644 locked.txt",
        stdout=("Permission denied",),
    ),
    SmokeTask(
        name="directory_replaces_file_error",
        seed={"clash": "i am a file\n"},
        script="mkdir clash 2>&1; echo status=$?",
        stdout=("File exists", "status=1"),
    ),
    SmokeTask(
        name="working_directory_changes",
        seed={"nest/inner.txt": "inside\n"},
        script="cd nest && cat inner.txt && /bin/pwd | grep -c nest",
        stdout=("inside", "1"),
    ),
    SmokeTask(
        name="relative_parent_paths",
        seed={"top.txt": "at the top\n", "down/here.txt": "below\n"},
        script="cd down && cat ../top.txt",
        stdout=("at the top",),
    ),
    SmokeTask(
        name="many_files_listing",
        script="for i in $(seq 1 200); do : > m$i; done; ls | wc -l",
        stdout=("200",),
    ),
    SmokeTask(
        name="empty_workspace_listing",
        script="ls -A | wc -l",
        stdout=("0",),
    ),
    # ------------------------------------------------------------------------
    # Local interception.  Here the Python interpreter *is* the agent, so these
    # syscalls are trapped and replayed rather than run on the target -- the
    # same path an agent's Read/Write/Edit tools take.
    # ------------------------------------------------------------------------
    SmokeTask(
        name="local_mkdir",
        runner="python",
        script="import os; os.mkdir('made'); print(os.path.isdir('made'))",
        stdout=("True",),
    ),
    SmokeTask(
        name="local_makedirs_nested",
        runner="python",
        script="import os; os.makedirs('a/b/c'); open('a/b/c/leaf.txt','w').write('deep')",
        target_files={"a/b/c/leaf.txt": "deep"},
    ),
    SmokeTask(
        name="local_write_file",
        runner="python",
        script="open('written.txt','w').write('by the interpreter')",
        target_files={"written.txt": "by the interpreter"},
    ),
    SmokeTask(
        name="local_read_file",
        runner="python",
        seed={"source.txt": "seeded on the target\n"},
        script="print(open('source.txt').read().strip())",
        stdout=("seeded on the target",),
    ),
    SmokeTask(
        name="local_append_to_file",
        runner="python",
        seed={"log.txt": "first\n"},
        script="open('log.txt','a').write('second\\n')",
        target_files={"log.txt": "first\nsecond\n"},
    ),
    SmokeTask(
        name="local_read_modify_write",
        runner="python",
        seed={"counter.txt": "41"},
        script=(
            "value = int(open('counter.txt').read());"
            "open('counter.txt','w').write(str(value + 1));"
            "print(open('counter.txt').read())"
        ),
        stdout=("42",),
        target_files={"counter.txt": "42"},
    ),
    SmokeTask(
        name="local_rename",
        runner="python",
        seed={"before.txt": "unchanged\n"},
        script="import os; os.rename('before.txt','after.txt'); print(open('after.txt').read())",
        stdout=("unchanged",),
        target_files={"after.txt": "unchanged\n"},
        target_missing=("before.txt",),
    ),
    SmokeTask(
        name="local_rename_keeps_unfetched_content",
        runner="python",
        seed={"lazy.txt": "never opened before the rename\n"},
        script=(
            "import os; os.rename('lazy.txt','moved.txt');print(open('moved.txt').read().strip())"
        ),
        stdout=("never opened before the rename",),
        target_files={"moved.txt": "never opened before the rename\n"},
    ),
    SmokeTask(
        name="local_unlink",
        runner="python",
        seed={"doomed.txt": "bye\n"},
        script="import os; os.remove('doomed.txt'); print(os.path.exists('doomed.txt'))",
        stdout=("False",),
        target_missing=("doomed.txt",),
    ),
    SmokeTask(
        name="local_rmdir",
        runner="python",
        seed={"box/.keep": ""},
        script="import os; os.remove('box/.keep'); os.rmdir('box'); print(os.path.exists('box'))",
        stdout=("False",),
        target_missing=("box",),
    ),
    SmokeTask(
        name="local_symlink",
        runner="python",
        seed={"real.txt": "pointed at\n"},
        script=(
            "import os; os.symlink('real.txt','alias.txt');"
            "print(os.readlink('alias.txt'), open('alias.txt').read().strip())"
        ),
        stdout=("real.txt pointed at",),
    ),
    SmokeTask(
        name="local_hardlink",
        runner="python",
        seed={"origin.txt": "shared\n"},
        script="import os; os.link('origin.txt','linked.txt'); print(open('linked.txt').read())",
        stdout=("shared",),
        target_files={"linked.txt": "shared\n"},
    ),
    SmokeTask(
        name="local_chmod",
        runner="python",
        seed={"script.sh": "echo hi\n"},
        script=(
            "import os, stat;"
            "os.chmod('script.sh', 0o755);"
            "print(oct(stat.S_IMODE(os.stat('script.sh').st_mode)))"
        ),
        stdout=("0o755",),
    ),
    SmokeTask(
        name="local_truncate",
        runner="python",
        seed={"trim.txt": "0123456789"},
        script="import os; os.truncate('trim.txt', 4); print(open('trim.txt').read())",
        stdout=("0123",),
        target_files={"trim.txt": "0123"},
    ),
    SmokeTask(
        name="local_listdir",
        runner="python",
        seed={"one.txt": "1\n", "two.txt": "2\n", "sub/three.txt": "3\n"},
        script="import os; print(sorted(os.listdir('.')))",
        stdout=("['one.txt', 'sub', 'two.txt']",),
    ),
    SmokeTask(
        name="local_walk",
        runner="python",
        seed={"x/1.txt": "1\n", "x/y/2.txt": "2\n"},
        script=(
            "import os;print(sorted(os.path.join(r, f) for r, _, fs in os.walk('.') for f in fs))"
        ),
        stdout=("['./x/1.txt', './x/y/2.txt']",),
    ),
    SmokeTask(
        name="local_stat_reports_target_size",
        runner="python",
        seed={"big.txt": "z" * 250_000},
        script="import os; print(os.stat('big.txt').st_size)",
        stdout=("250000",),
    ),
    SmokeTask(
        name="local_exists_checks",
        runner="python",
        seed={"here.txt": "x\n"},
        script="import os; print(os.path.exists('here.txt'), os.path.exists('nope.txt'))",
        stdout=("True False",),
    ),
    SmokeTask(
        name="local_mkdir_conflict_raises_eexist",
        runner="python",
        seed={"taken/.keep": ""},
        script=(
            "import errno, os\n"
            "try:\n"
            "    os.mkdir('taken')\n"
            "except FileExistsError as exc:\n"
            "    print('errno', errno.errorcode[exc.errno])\n"
        ),
        stdout=("errno EEXIST",),
    ),
    SmokeTask(
        name="local_unlink_missing_raises_enoent",
        runner="python",
        script=(
            "import errno, os\n"
            "try:\n"
            "    os.remove('ghost.txt')\n"
            "except FileNotFoundError as exc:\n"
            "    print('errno', errno.errorcode[exc.errno])\n"
        ),
        stdout=("errno ENOENT",),
    ),
    SmokeTask(
        name="local_utime",
        runner="python",
        seed={"stamped.txt": "x\n"},
        script=(
            "import os; os.utime('stamped.txt', (1_000_000_000, 1_000_000_000));"
            "print(int(os.stat('stamped.txt').st_mtime))"
        ),
        stdout=("1000000000",),
    ),
    SmokeTask(
        name="local_edit_then_remote_command_sees_it",
        runner="python",
        seed={"shared.py": "VALUE = 1\n"},
        script=(
            "import subprocess;"
            "open('shared.py','w').write('VALUE = 99\\n');"
            "print(subprocess.run(['grep','-o','99','shared.py'],"
            "capture_output=True,text=True).stdout.strip())"
        ),
        stdout=("99",),
        target_files={"shared.py": "VALUE = 99\n"},
    ),
    SmokeTask(
        name="local_cancels_a_running_remote_command",
        runner="python",
        script=(
            "import subprocess, time\n"
            "child = subprocess.Popen(['sh', '-c', 'sleep 60'])\n"
            "time.sleep(1.5)\n"
            "child.terminate()\n"
            "print('status', child.wait(timeout=40))\n"
        ),
        # The stand-in dies from the same signal the command received, so the
        # agent sees a signal death just as it would from a local child.
        stdout=("status -15",),
    ),
    SmokeTask(
        name="local_kills_a_running_remote_command",
        runner="python",
        script=(
            "import subprocess, time\n"
            "child = subprocess.Popen(['sh', '-c', 'sleep 60'])\n"
            "time.sleep(1.0)\n"
            "child.kill()\n"
            "print('status', child.wait(timeout=40))\n"
        ),
        stdout=("status -9",),
    ),
    SmokeTask(
        name="local_runs_commands_concurrently",
        runner="python",
        script=(
            "import subprocess, time\n"
            "start = time.monotonic()\n"
            "kids = [subprocess.Popen(['sh', '-c', f'sleep 2; echo done{i}'],\n"
            "                         stdout=subprocess.PIPE) for i in range(4)]\n"
            "out = sorted(k.communicate()[0].decode().strip() for k in kids)\n"
            "print(' '.join(out), 'elapsed_under_6', time.monotonic() - start < 6)\n"
        ),
        stdout=("done0 done1 done2 done3 elapsed_under_6 True",),
    ),
    SmokeTask(
        name="local_sees_what_a_remote_command_wrote",
        runner="python",
        script=(
            "import subprocess;"
            "subprocess.run(['sh','-c','echo made remotely > fresh.txt']);"
            "print(open('fresh.txt').read().strip())"
        ),
        stdout=("made remotely",),
        target_files={"fresh.txt": "made remotely\n"},
    ),
)
