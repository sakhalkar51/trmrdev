#!/usr/bin/env python3
"""trmrdev — launch a per-repo workspace in iTerm2. No tmux anywhere.

    trmrdev                   print the quick help
    trmrdev --no-upgrade      pick a repo with fzf and launch
    trmrdev --repo zeus       skip the picker
    trmrdev --upgrade         brew upgrade first

Installing and checking dependencies is not this file's job — that lives in
the Makefile beside it: `make install`, `make check`.

Layout (ported 1:1 from the tmux windows this replaced):

    Tab  claude    claude, in the repo root
    Tab  dev       3 panes — runserver (top-left), shell (bottom-left),
                   gitui (right, full height)
    Tab  editor    nvim with the file-tree sidebar focused

Where it lands:

    run from inside iTerm2  -> the tabs are added to THAT window
    run from anywhere else  -> iTerm2 is launched/raised and gets a window
                               (Terminal.app, Apple Shortcuts, Raycast, …)

Session persistence is gone by design: close the window and the workspace is
over, there is nothing to re-attach to. Navigation is iTerm2's own —
cmd-<n> for tabs, cmd-opt-<arrow> for panes.

Requires "Enable Python API" (iTerm2 > Settings > General > Magic).

On a machine with nothing installed, run `make install` first — this file
cannot run there at all, because its shebang needs a python3 that a Mac
without the Command Line Tools does not have. The Makefile is shell for
exactly that reason.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEV_ROOT = Path.home() / "dev"
ITERM_APP = Path("/Applications/iTerm.app")
TOOL_DIR = Path(__file__).resolve().parent
VENV = TOOL_DIR / "venv"
# iTerm2 only listens on this socket when the Python API is enabled; its
# absence is the difference between "not launched yet" and "not enabled".
API_SOCKET = (
    Path.home() / "Library/Application Support/iTerm2/private/socket"
)


def die(msg: str, code: int = 1) -> "None":
    print(f"trmrdev: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- bootstrap

def bootstrap() -> None:
    """Re-exec under the venv the Makefile built.

    This file never creates the venv: `make install` owns that, so there is one
    home for the rule and the installer stays runnable on a machine with no
    Python at all. Here we only hop into it, or say what to run.
    """
    venv_python = VENV / "bin" / "python"
    if not venv_python.exists():
        die(f"no venv yet — run: make -C {TOOL_DIR} install")
    if Path(sys.prefix) == VENV:
        # Already inside it and the import still failed, so the venv is real
        # but incomplete; rebuilding is the fix, not re-execing forever.
        die(f"the venv has no iterm2 module — run: make -C {TOOL_DIR} install")

    os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])


# The import that decides which interpreter we are running under. Failing it is
# the normal first step: the shebang starts us on the system python, where
# iterm2 does not exist, and bootstrap() re-execs us under the venv where it
# does. Keep this immediately after bootstrap() — it is the only thing that
# calls it, and without it every iterm2 reference below is a NameError.
try:
    import iterm2
except ImportError:
    bootstrap()


# ------------------------------------------------------------------ inputs

QUICK_HELP = """trmrdev — a per-repo workspace in iTerm2

  trmrdev --no-upgrade              pick a repo with fzf, then launch
  trmrdev --no-upgrade --repo zeus  skip the picker
  trmrdev --upgrade                 brew upgrade first, then launch
  trmrdev --help                    every launch option

Dependencies live in the Makefile, not here:

  make -C ~/trmrdev check           what is present and what is missing
  make -C ~/trmrdev install         install the missing, write the config

Bare `trmrdev` prints this. Skipping the upgrade is the default, so
--no-upgrade is how you say "just launch" out loud. Running it twice for the
same repo raises that workspace rather than building a second one."""


def parse_args(argv: list[str]) -> "tuple[bool, Path | None]":
    # Bare `trmrdev` says what it can do rather than launching something.
    if not argv:
        print(QUICK_HELP)
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="trmrdev",
        description="Launch a per-repo workspace in iTerm2: a claude tab, a "
        "3-pane dev tab, an editor tab, plus VS Code, Firefox and Slack. "
        "Dependencies are the Makefile's job: make install, make check.",
        epilog="Running trmrdev twice for the same repo raises the existing "
        "workspace instead of building a second one.",
    )

    upgrade = parser.add_mutually_exclusive_group()
    upgrade.add_argument(
        "--upgrade",
        dest="upgrade",
        action="store_true",
        help="run 'brew upgrade' before launching",
    )
    upgrade.add_argument(
        "--no-upgrade",
        dest="upgrade",
        action="store_false",
        help="skip the upgrade (the default)",
    )
    parser.set_defaults(upgrade=False)

    parser.add_argument(
        "--repo",
        metavar="PATH",
        help="a directory under ~/dev, by name or full path. Omit it to pick "
        "one with fzf — but it is required where there is no terminal for fzf "
        "to draw in, such as an Apple Shortcut.",
    )

    args = parser.parse_args(argv)

    repo = None
    if args.repo:
        repo = Path(args.repo).expanduser()
        if not repo.is_absolute():
            repo = DEV_ROOT / repo
        repo = repo.resolve()
        if not repo.is_dir():
            die(f"not a directory: {repo}")

    return args.upgrade, repo


def has_tty() -> bool:
    """fzf draws on /dev/tty, not stdin — a Shortcut has neither."""
    try:
        os.close(os.open("/dev/tty", os.O_RDONLY))
        return True
    except OSError:
        return False


def pick_repo() -> Path:
    if not DEV_ROOT.is_dir():
        die(f"{DEV_ROOT} does not exist")
    candidates = sorted(p for p in DEV_ROOT.iterdir() if p.is_dir())
    if not candidates:
        die(f"no repos under {DEV_ROOT}")

    if not has_tty():
        listing = "\n  ".join(p.name for p in candidates)
        die(
            "no terminal to draw fzf in — name the repo with --repo instead. "
            f"Available:\n  {listing}"
        )

    if not shutil.which("fzf"):
        die("fzf not found on PATH")

    picked = subprocess.run(
        ["fzf", "--prompt=trmrdev > "],
        input="\n".join(str(p) for p in candidates),
        capture_output=True,
        text=True,
    )
    chosen = picked.stdout.strip().splitlines()
    if picked.returncode != 0 or not chosen:
        sys.exit(0)  # cancelled
    return Path(chosen[0])


# ------------------------------------------------------------------- probes

def find_activate(repo: Path) -> "Path | None":
    """Both venv conventions live under ~/dev: `.venv/` (xenocrates, sitedump)
    and `venv/` (eninesites, zeus)."""
    for candidate in (repo / ".venv/bin/activate", repo / "venv/bin/activate"):
        if candidate.is_file():
            return candidate
    return None


def find_manage(repo: Path) -> "Path | None":
    """manage.py sits at the repo root in the single-project repos, but one
    level down in the pypkg+server shape (xenocrates: server/manage.py)."""
    if (repo / "manage.py").is_file():
        return repo / "manage.py"
    for child in sorted(repo.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            if (child / "manage.py").is_file():
                return child / "manage.py"
    return None


# -------------------------------------------------------------------- panes

class DevError(Exception):
    """A failure iTerm2 reported while building the workspace."""


class Pane:
    """One iTerm2 session: a label, a working directory, a command to land on.

    `setup` is the plumbing — cd, venv, pane label — and is wiped from the
    screen before `run` takes over, so the pane opens on its program (or a
    clean prompt), not on the lines this script typed to get there.

    `vertical` is how this pane is split off the tab's first pane — vertical
    means a left|right divider, matching tmux's `split-window -h`.
    """

    def __init__(
        self,
        label: str,
        cwd: Path,
        *setup: str,
        run: str = "",
        vertical: bool = False,
    ) -> None:
        self.label = label
        self.cwd = cwd
        self.vertical = vertical

        # Every pane carries its own cd. A profile customization would be
        # tidier, but it cannot reach the one tab we adopt rather than create
        # (the window a cold iTerm2 opens for itself), which would leave claude
        # running in $HOME. One mechanism, correct everywhere.
        #
        # The pane label is set from inside the shell rather than over the API.
        # oh-my-zsh's termsupport rewrites the name in preexec — which fires on
        # this very line, after any name we could have set beforehand — so the
        # only ordering that survives is: disable it, then set the title as a
        # step of the line itself. DISABLE_AUTO_TITLE is read at hook time, so
        # exporting it here is enough, and it is scoped to this pane; other
        # shells keep their cwd titles.
        #
        # `clear` is the last plumbing step: \033[3J takes the scrollback with
        # it, so the typed line is gone rather than one page up. It has to come
        # before `run`, because `run` is usually a program that never returns.
        steps = [
            "export DISABLE_AUTO_TITLE=true",
            f"cd {shlex.quote(str(cwd))}",
            f"printf '\\033]0;%s\\a' {shlex.quote(label)}",
            *(s for s in setup if s),
            "clear && printf '\\033[3J'",
        ]
        if run:
            steps.append(run)
        self.command = " && ".join(steps)

    async def dress(self, session) -> None:
        await session.async_send_text(self.command + "\n")


def plan(repo: Path) -> "dict[str, list[Pane]]":
    activate = find_activate(repo)
    manage = find_manage(repo)
    source = f"source {shlex.quote(str(activate))}" if activate else ""

    server = Pane(
        "server",
        manage.parent if manage else repo,
        source,
        run="python manage.py runserver" if manage else "",
    )
    # Order matters: gitui is split off first while `server` still owns the
    # full width, so it keeps full height; shell then splits the left column.
    return {
        "claude": [Pane("claude", repo, source, run="claude")],
        "dev": [
            server,
            Pane("gitui", repo, run="gitui", vertical=True),
            Pane("shell", repo, source, vertical=False),
        ],
        "editor": [Pane("editor", repo, run="nvim +NvimTreeFocus")],
    }


# ------------------------------------------------------------- desktop apps

# (app name, System Events process name, opens the repo). The process name is
# not derivable from the app name — Firefox Developer Edition reports itself as
# lowercase "firefox", and Visual Studio Code as "Code".
DESKTOP_APPS = (
    ("Visual Studio Code", "Code", True),
    ("Firefox Developer Edition", "firefox", False),
    ("Slack", "Slack", False),
)

# macOS exposes native fullscreen only as an accessibility attribute, so this
# needs Accessibility permission for whichever app runs dev — iTerm2 normally,
# Terminal or Shortcuts otherwise. Nothing else drives it: none of these three
# apps has an AppleScript dictionary, and no launch flag opens them fullscreen.
# Strictly a setter, never a toggle, and a no-op when the window is already
# fullscreen. An earlier version left fullscreen and re-entered it; exiting
# starts an animation that the re-entry races, so apps which launched already
# fullscreen ended up windowed. Leaving a fullscreen window alone is both
# correct and idempotent.
FULLSCREEN = """
tell application "System Events"
  tell process "{process}"
    set waited to 0
    repeat until (count of windows) > 0 or waited > 80
      delay 0.25
      set waited to waited + 1
    end repeat
    if (count of windows) is 0 then error "no accessibility window"
    if not (value of attribute "AXFullScreen" of window 1) then
      set frontmost to true
      set value of attribute "AXFullScreen" of window 1 to true
    end if
  end tell
end tell
"""

NO_ACCESSIBILITY = (
    "not allowed assistive access",
    "assistive access",
)


def start_desktop_apps(repo: Path) -> None:
    """Launch the companion apps without waiting for them to finish opening.

    Fullscreen comes later, so the apps get their startup time for free while
    the iTerm2 workspace is being built.
    """
    for name, _, opens_repo in DESKTOP_APPS:
        if not (Path("/Applications") / f"{name}.app").is_dir():
            print(f"trmrdev: {name} is not installed, skipping", file=sys.stderr)
            continue
        argv = ["open", "-a", name]
        if opens_repo:
            argv.append(str(repo))
        subprocess.run(argv, check=False)


def fullscreen_desktop_apps() -> None:
    """Send each running companion app to its own Space."""
    denied = False
    for name, process, _ in DESKTOP_APPS:
        if not (Path("/Applications") / f"{name}.app").is_dir():
            continue
        result = subprocess.run(
            ["osascript", "-e", FULLSCREEN.format(process=process)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            continue

        error = result.stderr.strip()
        if any(marker in error for marker in NO_ACCESSIBILITY):
            denied = True
            break

        # System Events can only enumerate windows on the ACTIVE Space, so an
        # app that is already fullscreen on a Space of its own reports no
        # window at all. That is the steady state this aims for, not a fault,
        # and it is silent on purpose. Forcing the issue with the ctrl-cmd-F
        # menu shortcut is not an option either: it toggles, so firing it
        # blindly turns fullscreen OFF for exactly the apps already correct.
        # These apps remember fullscreen across launches, so one manual
        # ctrl-cmd-F is all any of them ever needs.
        if "no accessibility window" in error:
            continue

        print(f"trmrdev: could not fullscreen {name} ({error})", file=sys.stderr)

    if denied:
        print(
            "trmrdev: fullscreen needs Accessibility permission.\n"
            "  Grant it to the app you run dev from (iTerm2, Terminal, "
            "Shortcuts) in\n"
            "  System Settings > Privacy & Security > Accessibility, then run "
            "dev again.\n"
            "  The workspace itself is up; only the other apps are not "
            "fullscreen.",
            file=sys.stderr,
        )


# ------------------------------------------------------------------- iTerm2

def iterm_running() -> bool:
    return subprocess.run(["pgrep", "-qx", "iTerm2"]).returncode == 0


def ensure_iterm() -> bool:
    """Launch iTerm2 if needed. Returns True if we were the one to launch it."""
    if not ITERM_APP.is_dir():
        die(f"iTerm2 not found at {ITERM_APP}")
    if iterm_running():
        return False

    # `open` hands our environment to the app it launches, and every pane's
    # shell then inherits it from iTerm2. Running `dev` from inside a Claude
    # Code session would otherwise leak CLAUDE_CODE_CHILD_SESSION into the new
    # claude, which silently disables its transcript saving. Hand iTerm2 a
    # clean environment; ~/.zshrc re-establishes anything intentional.
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    subprocess.run(["open", "-a", str(ITERM_APP)], check=True, env=env)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if API_SOCKET.exists():
            time.sleep(0.5)  # let the restored/default window settle
            return True
        time.sleep(0.1)
    die(
        "iTerm2 started but never opened its API socket.\n"
        "  Enable it: iTerm2 > Settings > General > Magic > Enable Python API"
    )
    return True  # unreachable


def launching_window(app):
    """The window this script was run from, or None if we are not in iTerm2.

    iTerm2 stamps every session's shell with ITERM_SESSION_ID = wNtNpN:<guid>,
    and <guid> is the session's API id. Matching on it beats current_window,
    which is merely whatever is frontmost — wrong the moment focus moves while
    fzf is up.
    """
    stamp = os.environ.get("ITERM_SESSION_ID", "")
    if not stamp:
        return None
    guid = stamp.rsplit(":", 1)[-1]
    for window in app.terminal_windows:
        for tab in window.tabs:
            for session in tab.sessions:
                if session.session_id == guid:
                    return window
    return None


def claimable_window(app):
    """A freshly launched iTerm2 opens a window of its own; adopt it rather
    than leaving an empty orphan behind. Anything else — a restored
    arrangement, several windows — is left alone and gets a new window."""
    windows = app.terminal_windows
    if len(windows) != 1:
        return None
    tabs = windows[0].tabs
    if len(tabs) != 1 or len(tabs[0].sessions) != 1:
        return None
    return windows[0]


# Stamped on every workspace window so a second run for the same repo finds
# the first one instead of stacking another three tabs onto it. iTerm2 only
# accepts user-defined variables under the "user." prefix.
REPO_TAG = "user.devRepo"


async def existing_workspace(app, repo: Path):
    """The window already holding this repo's workspace, if there is one."""
    for window in app.terminal_windows:
        if await window.async_get_variable(REPO_TAG) == str(repo):
            return window
    return None


async def build(
    connection,
    layout: "dict[str, list[Pane]]",
    we_launched: bool,
    repo: Path,
) -> bool:
    """Build the workspace, or focus it if it is already up.

    Returns True when an existing workspace was reused. Running dev twice for
    the same repo is a no-op beyond raising the window, which is the whole
    point — the tabs, panes and servers are already there.
    """
    app = await iterm2.async_get_app(connection)

    window = await existing_workspace(app, repo)
    if window is not None:
        await window.async_activate()
        await window.async_set_fullscreen(True)
        await app.async_activate()
        return True

    window = launching_window(app)
    # A window that is already someone else's workspace is not a host for this
    # one; leave it alone and open a new window instead of mixing two repos.
    if window is not None and await window.async_get_variable(REPO_TAG):
        window = None

    claim_first_tab = False
    if window is None:
        window = claimable_window(app) if we_launched else None
        if window is None:
            window = await iterm2.Window.async_create(connection)
            if window is None:
                raise DevError("iTerm2 refused to create a window")
        claim_first_tab = True

    first_tab = None
    for title, panes in layout.items():
        head, *rest = panes

        if claim_first_tab and first_tab is None:
            tab = window.current_tab
        else:
            tab = await window.async_create_tab()
            if tab is None:
                raise DevError(f"iTerm2 refused to create the {title} tab")

        session = tab.current_session
        await head.dress(session)

        # Every split is taken off the tab's first pane, so the declared order
        # is the geometry: gitui right at full height, then shell under server.
        for pane in rest:
            new = await session.async_split_pane(vertical=pane.vertical)
            await pane.dress(new)

        # A pinned tab title; oh-my-zsh's termsupport rewrites session titles
        # on every prompt, but it cannot touch a tab title override.
        await tab.async_set_title(title)
        if first_tab is None:
            first_tab = tab

    await window.async_set_variable(REPO_TAG, str(repo))
    await first_tab.async_select()
    await window.async_activate()
    await app.async_activate()
    await window.async_set_fullscreen(True)
    return False


# --------------------------------------------------------------------- main

def main() -> None:
    upgrade, repo = parse_args(sys.argv[1:])

    if upgrade:
        print("Running brew upgrade...")
        subprocess.run(["brew", "upgrade"])

    if repo is None:
        repo = pick_repo()
    layout = plan(repo)

    # Started before the workspace is built, not after: launching is instant
    # but these apps take seconds to draw a window, and they spend that time
    # usefully while iTerm2 is being set up.
    start_desktop_apps(repo)

    we_launched = ensure_iterm()

    # A list, because run_until_complete discards whatever the coroutine
    # returns and this needs to survive back out to report on.
    reused: list[bool] = []

    async def run(connection) -> None:
        reused.append(await build(connection, layout, we_launched, repo))

    try:
        iterm2.run_until_complete(run)
    except DevError as error:
        die(str(error))
    except (ConnectionRefusedError, OSError) as error:
        die(unreachable(error))
    except SystemExit as error:
        # run_until_complete swallows a refused connection into sys.exit(1).
        if error.code in (None, 0):
            raise
        die(unreachable(error))

    if reused and reused[0]:
        print(f"trmrdev: {repo.name} workspace already up, raising it", file=sys.stderr)

    fullscreen_desktop_apps()
    # Fullscreening the companions left the screen on Slack's Space; come back
    # to iTerm2, which is where the work starts.
    subprocess.run(["open", "-a", str(ITERM_APP)], check=False)


def unreachable(error: BaseException) -> str:
    return (
        "could not reach iTerm2's Python API.\n"
        "  Enable it: iTerm2 > Settings > General > Magic > Enable Python API\n"
        f"  ({type(error).__name__}: {error})"
    )


if __name__ == "__main__":
    main()
