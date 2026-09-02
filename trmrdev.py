#!/usr/bin/env python3
"""trmrdev — launch a per-repo workspace in Ghostty. No tmux anywhere.

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
    Tab  editor    nvim with the file explorer open

Where it lands:

    Ghostty is launched if needed, and each workspace gets its own window.
    Packing up closes only the tabs this tool made, so a window you were
    already using survives.

Session persistence is gone by design: close the window and the workspace is
over, there is nothing to re-attach to. Navigation is
Ghostty's own: cmd-<n> for tabs, cmd-opt-<arrow> for panes.

Ghostty is driven over AppleScript, so there is nothing to enable and no
third-party module to install — hence no venv.

On a machine with nothing installed, run `make install` first — this file
cannot run there at all, because its shebang needs a python3 that a Mac
without the Command Line Tools does not have. The Makefile is shell for
exactly that reason.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

DEV_ROOT = Path.home() / "dev"
TOOL_DIR = Path(__file__).resolve().parent


def die(msg: str, code: int = 1) -> "None":
    print(f"trmrdev: {msg}", file=sys.stderr)
    sys.exit(code)


# ------------------------------------------------------------------ inputs

QUICK_HELP = """trmrdev — a per-repo workspace in Ghostty

  trmrdev -nu                       pick a repo with fzf, then launch
  trmrdev -nu --repo zeus           skip the picker
  trmrdev -u                        brew upgrade first, then launch
  trmrdev -p                        pack up a workspace: pick from what is open
  trmrdev -p --repo zeus            pack up that one
  trmrdev --help                    every launch option

The long forms all still work: -nu is --no-upgrade, -u is --upgrade,
-p is --pack-up.

Dependencies live in the Makefile, not here:

  make -C ~/trmrdev check           what is present and what is missing
  make -C ~/trmrdev install         install the missing, write the config

Bare `trmrdev` prints this. Skipping the upgrade is the default, so
--no-upgrade is how you say "just launch" out loud. Running it twice for the
same repo raises that workspace rather than building a second one."""


def parse_args(argv: list[str]) -> "tuple[bool, Path | None, bool]":
    # Bare `trmrdev` says what it can do rather than launching something.
    if not argv:
        print(QUICK_HELP)
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="trmrdev",
        description="Launch a per-repo workspace in Ghostty: a claude tab, a "
        "3-pane dev tab, an editor tab, plus VS Code, Firefox and Slack. "
        "Dependencies are the Makefile's job: make install, make check.",
        epilog="Running trmrdev twice for the same repo raises the existing "
        "workspace instead of building a second one.",
    )

    upgrade = parser.add_mutually_exclusive_group()
    upgrade.add_argument(
        "-u", "--upgrade",
        dest="upgrade",
        action="store_true",
        help="run 'brew upgrade' before launching",
    )
    # argparse accepts a multi-character single-dash option, and -nu is
    # unambiguous here only because no -n exists to combine with.
    upgrade.add_argument(
        "-nu", "--no-upgrade",
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

    parser.add_argument(
        "-p", "--pack-up",
        dest="pack_up",
        action="store_true",
        help="pack up the workspace for --repo instead of opening it: the "
        "tabs it created, its dev servers, and any app this tool started for "
        "it. The window itself and any tab you opened are left alone. "
        "Without --repo, pick from the workspaces that are open.",
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

    return args.upgrade, repo, args.pack_up


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
    """A failure reported while building the workspace."""


class Pane:
    """One terminal: a label, a working directory, a command to land on.

    `setup` is the plumbing — venv, pane label — and is wiped from the
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

        # No `cd` here: Ghostty's surface configuration sets the working
        # directory at birth (see config_for), so the terminal starts where it
        # belongs instead of walking there in full view.
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
            f"printf '\\033]0;%s\\a' {shlex.quote(label)}",
            *(s for s in setup if s),
            "clear && printf '\\033[3J'",
        ]
        if run:
            steps.append(run)
        self.command = " && ".join(steps)


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
        # :Neotree exists because the overlay enables LazyVim's neo-tree
        # extra; stock LazyVim 14+ ships the snacks explorer instead and this
        # command would fail.
        "editor": [Pane("editor", repo, run="nvim +Neotree")],
    }


# ------------------------------------------------------------------- state

# What each open workspace opened, so closing undoes exactly that and no more.
# Kept outside the tool directory on purpose: that directory is what gets
# zipped and shared, and this is machine state, not part of the program.
STATE_FILE = Path.home() / ".local/state/trmrdev/workspaces.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))


def app_running(app_name: str) -> bool:
    """True if that .app has a live process, asked by bundle rather than name.

    pgrep is not trustworthy here: it fails to match Ghostty at all — not by
    name, not with -f against the full command line — even while Ghostty is
    the parent of the shell asking. `ps` sees it. Getting this wrong is not
    cosmetic: a false "not running" makes the launcher believe it started
    Ghostty, and the build then closes every pre-existing window as startup
    litter.

    Matching the bundle path also sidesteps guessing executable names, which
    do not follow the app (VS Code runs as Electron, Firefox Developer
    Edition as firefox).
    """
    listing = subprocess.run(
        ["ps", "-eo", "comm"], capture_output=True, text=True
    ).stdout
    return f"/{app_name}.app/" in listing


def quit_app(name: str) -> bool:
    return subprocess.run(
        ["osascript", "-e", f'tell application "{name}" to quit'],
        capture_output=True,
    ).returncode == 0


def repo_servers(repo: Path) -> "list[int]":
    """PIDs of dev servers running inside this repo.

    Closing the window SIGHUPs its shells, but a runserver started in a pane
    routinely survives that and keeps the port — so closing up has to find and
    end them by working directory rather than trusting the window to do it.
    """
    found = subprocess.run(
        ["pgrep", "-f", "manage.py runserver"], capture_output=True, text=True
    )
    pids = []
    for pid in found.stdout.split():
        cwd = subprocess.run(
            ["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
            capture_output=True, text=True,
        ).stdout
        for line in cwd.splitlines():
            if not line.startswith("n"):
                continue
            path = line[1:]
            if path == str(repo) or path.startswith(f"{repo}/"):
                pids.append(int(pid))
                break
    return pids


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
# needs Accessibility permission for whichever app runs trmrdev — Ghostty,
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


def start_desktop_apps(repo: Path) -> "list[str]":
    """Launch the companion apps; return the ones this run actually started.

    Fullscreen comes later, so the apps get their startup time for free while
    the workspace is being built.

    Whether *we* started an app decides whether --pack-up may quit it later. An
    app the owner already had open is not ours to close, and the only moment
    that is knowable is here, before we launch anything.
    """
    launched = []
    for name, process, opens_repo in DESKTOP_APPS:
        if not (Path("/Applications") / f"{name}.app").is_dir():
            print(f"trmrdev: {name} is not installed, skipping", file=sys.stderr)
            continue
        was_running = app_running(name)
        argv = ["open", "-a", name]
        if opens_repo:
            argv.append(str(repo))
        subprocess.run(argv, check=False)
        if not was_running:
            launched.append(name)
    return launched


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
            "  Grant it to the app you run trmrdev from (Ghostty, Terminal, "
            "Shortcuts) in\n"
            "  System Settings > Privacy & Security > Accessibility, then run "
            "trmrdev again.\n"
            "  The workspace itself is up; only the other apps are not "
            "fullscreen.",
            file=sys.stderr,
        )


# ------------------------------------------------------------------ Ghostty

GHOSTTY_APP = Path("/Applications/Ghostty.app")

# The tab titles this tool pins. Ghostty's `tab.name` is read-only over
# AppleScript, unlike iTerm2's titleOverride, so the title is set from inside
# the pane instead — see Pane. These names are what a tab is recognised by when
# the state file cannot be trusted.
TAB_TITLES = ("claude", "dev", "editor")


class GhosttyError(Exception):
    """Ghostty refused something we asked of it."""


def osa(script: str) -> str:
    """Run one AppleScript against Ghostty and hand back its result."""
    done = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True
    )
    if done.returncode != 0:
        raise GhosttyError(done.stderr.strip() or "osascript failed")
    return done.stdout.strip()


def as_str(text: str) -> str:
    """A safe AppleScript string literal. Backslash and quote are the only two
    characters that need escaping."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def config_for(pane: "Pane") -> str:
    """A Ghostty surface configuration record for one pane.

    This is what replaces the `cd` that every iTerm2 pane had to carry: the
    working directory and the first input are given to the surface at birth,
    so the terminal starts where it belongs instead of walking there.
    """
    parts = [f"initial working directory:{as_str(pane.cwd)}"]
    if pane.command:
        parts.append(f"initial input:{as_str(pane.command + chr(10))}")
    return "{" + ", ".join(parts) + "}"


def ghostty_running() -> bool:
    return app_running("Ghostty")


def ensure_ghostty() -> bool:
    """Launch Ghostty if needed. True if we were the one to launch it."""
    if not GHOSTTY_APP.is_dir():
        die(f"Ghostty is not installed at {GHOSTTY_APP}")
    if ghostty_running():
        return False
    # `open` hands our environment to the app it launches, and every pane's
    # shell inherits it. Running trmrdev from inside a Claude Code session
    # would otherwise leak CLAUDE_CODE_CHILD_SESSION into the new claude,
    # silently disabling its transcript saving.
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    subprocess.run(["open", "-a", str(GHOSTTY_APP)], check=True, env=env)
    for _ in range(60):
        if ghostty_running():
            time.sleep(1.0)   # let the first window settle
            return True
        time.sleep(0.25)
    die("Ghostty did not start")
    return False   # unreachable


def build(layout: "dict[str, list[Pane]]", repo: Path, drop_startup_window: bool = False) -> "tuple[str, list[str]]":
    """Build the whole workspace in one AppleScript, returning (window, tabs).

    One script rather than a call per tab: it is atomic from Ghostty's point of
    view and avoids a dozen osascript round trips, each of which costs an
    interpreter launch.
    """
    claude, dev, editor = layout["claude"], layout["dev"], layout["editor"]
    server, gitui, shell = dev

    # A cold Ghostty opens a window of its own before we ask for anything.
    # Ours is a second one, so the startup window is left over — collect it
    # first and close it at the end. Only ever when WE launched Ghostty:
    # otherwise those are the owner's windows, not litter.
    capture = "set stale to every window" if drop_startup_window else "set stale to {}"
    dismiss = (
        "repeat with old in stale\n    try\n      close window old\n    end try\n  end repeat"
        if drop_startup_window else ""
    )

    script = f"""
tell application "Ghostty"
  activate
  {capture}
  set w to new window with configuration {config_for(claude[0])}
  delay 0.6
  -- Hold the tab itself, not its index: `tab 1 of w` is not addressable
  -- ("Access not allowed"), and select tab wants a reference anyway.
  set claudeTab to selected tab of w
  set tabIds to (id of claudeTab)

  set devTab to new tab in w with configuration {config_for(server)}
  delay 0.6
  set serverTerm to focused terminal of devTab
  -- gitui is split off first, while the server pane still owns the full
  -- width, so it keeps full height on the right; the shell then halves the
  -- left column. The declared order in plan() is the geometry.
  split serverTerm direction right with configuration {config_for(gitui)}
  delay 0.4
  split serverTerm direction down with configuration {config_for(shell)}
  set tabIds to tabIds & "," & (id of devTab)

  set edTab to new tab in w with configuration {config_for(editor[0])}
  delay 0.4
  set tabIds to tabIds & "," & (id of edTab)

  select tab claudeTab
  activate window w
  -- Only ever fullscreen a window we just made. The Ghostty action is a
  -- TOGGLE with no readable state, so applying it to an existing window
  -- would take it OUT of fullscreen — the same trap the companion apps set.
  perform action "toggle_fullscreen" on (focused terminal of (selected tab of w))

  {dismiss}
  return (id of w) & "|" & tabIds
end tell
"""
    out = osa(script)
    if "|" not in out:
        raise GhosttyError(f"unexpected result from Ghostty: {out!r}")
    window_id, tabs = out.split("|", 1)
    return window_id, [t for t in tabs.split(",") if t]


def workspace_tabs(repo: Path, window_id: str = "") -> "tuple[str, list[str]]":
    """Find an open workspace for this repo: (window id, our tab ids).

    Identity comes from the terminals' working directory rather than a tag —
    Ghostty has no user-defined variables, and the directory is the truer fact
    anyway. A run that died before saving state is still findable this way.
    """
    if not ghostty_running():
        return "", []

    script = f"""
tell application "Ghostty"
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      repeat with term in terminals of t
        if (working directory of term) is {as_str(repo)} then
          set out to out & (id of w) & " " & (id of t) & linefeed
          exit repeat
        end if
      end repeat
    end repeat
  end repeat
  return out
end tell
"""
    try:
        out = osa(script)
    except GhosttyError:
        return "", []

    windows: dict = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            windows.setdefault(parts[0], []).append(parts[1])
    if not windows:
        return "", []
    if window_id and window_id in windows:
        return window_id, windows[window_id]
    first = next(iter(windows))
    return first, windows[first]


def raise_workspace(window_id: str) -> None:
    """Bring the workspace forward. `open` raises the app without AppleScript;
    only picking out the specific window needs a script."""
    subprocess.run(["open", "-a", str(GHOSTTY_APP)], check=False)
    if not window_id:
        return
    try:
        osa(
            'tell application "Ghostty" to activate window '
            f"(first window whose id is {as_str(window_id)})"
        )
    except GhosttyError:
        pass


def close_tabs(tab_ids: "list[str]") -> int:
    """Close exactly these tabs. Never the window.

    Ghostty has no way to address a tab by id directly — `tab of windows whose
    id is ...` filters the WINDOWS, which silently matches nothing and closes
    nothing — so the tabs are walked and compared. One script for all of them,
    rather than an osascript launch each.

    If they were the only tabs, Ghostty closes the emptied window itself; a
    window you were already using keeps its own tabs and stays open.
    """
    if not tab_ids:
        return 0

    wanted = "{" + ", ".join(as_str(t) for t in tab_ids) + "}"
    script = f"""
tell application "Ghostty"
  set wanted to {wanted}
  -- Close one, then rescan. AppleScript references are POSITIONAL: closing
  -- `tab 1` renumbers everything after it, so a reference collected earlier
  -- now points at a different tab. Collecting first and closing second still
  -- closed two of three. Matching by id after every close is the only stable
  -- way. Three tabs, so the rescan costs nothing.
  set closed to 0
  repeat
    set hit to false
    repeat with w in (every window)
      repeat with t in (every tab of w)
        if (id of t) is in wanted then
          close tab t
          set closed to closed + 1
          set hit to true
          exit repeat
        end if
      end repeat
      if hit then exit repeat
    end repeat
    if not hit then exit repeat
  end repeat
  return closed
end tell
"""
    before = len(surviving_tabs(tab_ids))
    try:
        osa(script)
    except GhosttyError:
        pass   # closing the last tab takes the window with it, which the
               # script can report as an error after the work is done
    return before - len(surviving_tabs(tab_ids))


def surviving_tabs(tab_ids: "list[str]") -> "list[str]":
    """Which of these tab ids Ghostty still has.

    The close script's own return value is not trustworthy: closing the last
    tab closes the window under it, and the script can fail *after* doing the
    work — which reported nothing closed while three tabs had gone. Counting
    before and after is the honest measure.
    """
    if not tab_ids or not ghostty_running():
        return []
    wanted = "{" + ", ".join(as_str(t) for t in tab_ids) + "}"
    script = f"""
tell application "Ghostty"
  set found to ""
  repeat with w in (every window)
    repeat with t in (every tab of w)
      if (id of t) is in {wanted} then set found to found & (id of t) & linefeed
    end repeat
  end repeat
  return found
end tell
"""
    try:
        return [x for x in osa(script).splitlines() if x.strip()]
    except GhosttyError:
        return []


# --------------------------------------------------------------------- main

def main() -> None:
    upgrade, repo, packing_up = parse_args(sys.argv[1:])

    if packing_up:
        pack_up_workspace(repo or pick_open_workspace())
        return

    if upgrade:
        print("Running brew upgrade...")
        subprocess.run(["brew", "upgrade"])

    if repo is None:
        repo = pick_repo()
    layout = plan(repo)

    # Started before the workspace is built, not after: launching is instant
    # but these apps take seconds to draw a window, and they spend that time
    # usefully while the workspace is being set up.
    launched = start_desktop_apps(repo)

    we_launched = ensure_ghostty()

    window_id, existing = workspace_tabs(repo)
    if existing:
        raise_workspace(window_id)
        made = existing
        print(f"trmrdev: {repo.name} workspace already up, raising it", file=sys.stderr)
    else:
        try:
            window_id, made = build(layout, repo, drop_startup_window=we_launched)
        except GhosttyError as error:
            die(f"Ghostty refused to build the workspace: {error}")

    # Record what is open so --pack-up can undo exactly this. Re-opening merges
    # rather than overwrites: the second run launches nothing, and forgetting
    # what the first run started would strand those apps open forever.
    state = load_state()
    entry = state.get(str(repo), {})
    entry["launched"] = sorted(set(entry.get("launched", [])) | set(launched))
    entry["tabs"] = made or entry.get("tabs", [])
    entry["window"] = window_id or entry.get("window", "")
    entry["opened"] = entry.get("opened") or time.strftime("%Y-%m-%d %H:%M:%S")
    state[str(repo)] = entry
    save_state(state)

    fullscreen_desktop_apps()
    # Fullscreening the companions left the screen on Slack's Space; come back
    # to the terminal, which is where the work starts.
    subprocess.run(["open", "-a", str(GHOSTTY_APP)], check=False)



# ------------------------------------------------------------------ pack up

def pack_up_workspace(repo: Path) -> None:
    """Pack up one open workspace, undoing only what that open did.

    Idempotent in both directions: closing what is already closed reports so
    and changes nothing, and every step below is skipped when its target is
    already gone.
    """
    state = load_state()
    entry = state.pop(str(repo), None)

    servers = repo_servers(repo)
    for pid in servers:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    tab_ids = list(entry.get("tabs", [])) if entry else []
    # No record does not mean nothing is open: a workspace built before state
    # tracking, or by a run that died before saving, still has real tabs. Ask
    # Ghostty which of its terminals sit in this repo.
    if not tab_ids:
        _, tab_ids = workspace_tabs(repo, entry.get("window", "") if entry else "")

    tabs_closed = close_tabs(tab_ids)

    # Quit only what this workspace started, and only once no other workspace
    # is still relying on it. Apps are machine-wide but workspaces are not, so
    # the last one out turns the lights off.
    ours = list(entry.get("launched", [])) if entry else []
    quit_names: list[str] = []
    if ours and not state:
        for name in ours:
            if quit_app(name):
                quit_names.append(name)
    elif ours:
        remaining = ", ".join(sorted(Path(k).name for k in state))
        print(
            f"trmrdev: leaving {', '.join(ours)} open — still needed by {remaining}",
            file=sys.stderr,
        )

    save_state(state)

    if not (entry or tabs_closed or servers):
        print(f"trmrdev: nothing open for {repo.name}", file=sys.stderr)
        return

    did = []
    if tabs_closed:
        did.append(f"{tabs_closed} tab{'s' if tabs_closed > 1 else ''}")
    if servers:
        did.append(f"{len(servers)} dev server{'s' if len(servers) > 1 else ''}")
    if quit_names:
        did.append(", ".join(quit_names))
    print(f"trmrdev: closed {repo.name} ({'; '.join(did) or 'state only'})", file=sys.stderr)


def pick_open_workspace() -> Path:
    """Which workspace to close, chosen from the ones actually open."""
    state = load_state()
    if not state:
        die("no workspaces are open")
    keys = sorted(state)
    if len(keys) == 1:
        return Path(keys[0])
    if not has_tty() or not shutil.which("fzf"):
        listing = "\n  ".join(Path(k).name for k in keys)
        die(f"name the one to close with --repo. Open:\n  {listing}")
    picked = subprocess.run(
        ["fzf", "--prompt=close > "],
        input="\n".join(keys), capture_output=True, text=True,
    )
    chosen = picked.stdout.strip().splitlines()
    if picked.returncode != 0 or not chosen:
        sys.exit(0)
    return Path(chosen[0])


if __name__ == "__main__":
    main()
