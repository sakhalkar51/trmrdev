#!/usr/bin/env python3
"""Per-repo dev workspace launcher for Hyprland/Omarchy.

Hyprland/Omarchy port of the macOS trmrdev tool (../macos). Ghostty tabs
become separate Ghostty windows, one Hyprland workspace per pane
(claude/dev/editor), identified by window title so the launcher can find its
own windows again without trusting a state file. See omarchy/README.md.

Panes live on NUMBERED workspaces from config.NUMBERED_WORKSPACE_POOL, not
named ones: Omarchy's default SUPER+1-9/0 bindings switch to a specific
workspace ID and never traverse named workspaces, so a named workspace is
invisible to that keyboard workflow no matter what this script does. A pane
claims whatever pool slot is free and gives it back once packed up.

Usage:
    launcher.py open [--repo NAME]   # fzf-pick under config.REPO_ROOT if omitted
    launcher.py pack [--repo NAME]   # fzf-pick from currently open repos if omitted
"""

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

from config import NUMBERED_WORKSPACE_POOL, PANE_ORDER, PANES, REPO_ROOT, SHARED_APPS, SHARED_APPS_ORDER, TITLE_PREFIX


# --------------------------------------------------------------------- hyprctl


def lua_string(s: str) -> str:
    """Escape a Python string as a Lua double-quoted string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def hypr_dispatch(lua_expr: str) -> None:
    subprocess.run(["hyprctl", "dispatch", lua_expr], capture_output=True, text=True)


def hypr_clients() -> list[dict]:
    out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def exec_cmd(shell_cmd: str, workspace: str | None = None) -> None:
    """Run a shell command via Hyprland, optionally opening on a given workspace.

    The workspace rule is a best-effort request: Hyprland's exec_cmd tracks the
    spawned PID, so a command that forks before opening a window (Chromium's
    setsid/uwsm-app chain, for web apps) won't land on the requested workspace.
    Ghostty spawns directly, so this is reliable for the per-repo windows.
    """
    rules = f'{{ workspace = {lua_string(workspace)} }}' if workspace else "{}"
    hypr_dispatch(f"hl.dsp.exec_cmd({lua_string(shell_cmd)}, {rules})")


def focus_address(address: str) -> None:
    hypr_dispatch(f'hl.dsp.focus({{ window = {lua_string("address:" + address)} }})')


def move_and_focus(address: str, workspace: str) -> None:
    hypr_dispatch(
        f'hl.dsp.window.move({{ window = {lua_string("address:" + address)}, workspace = {lua_string(workspace)} }})'
    )
    focus_address(address)


def close_address(address: str) -> None:
    hypr_dispatch(f'hl.dsp.window.close({{ window = {lua_string("address:" + address)} }})')


def find_by_title(title: str, clients: list[dict] | None = None) -> dict | None:
    clients = clients if clients is not None else hypr_clients()
    for c in clients:
        if c["title"] == title or c["initialTitle"] == title:
            return c
    return None


def find_by_class(klass: str, clients: list[dict] | None = None) -> dict | None:
    clients = clients if clients is not None else hypr_clients()
    for c in clients:
        if c["class"] == klass:
            return c
    return None


def poll_for_class(klass: str, timeout: float = 8.0, interval: float = 0.3) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        c = find_by_class(klass)
        if c:
            return c["address"]
        time.sleep(interval)
    return None


# ------------------------------------------------------------------- ghostty


def build_ghostty_cmd(title: str, cwd: Path, inner_command: str | None) -> str:
    argv = ["ghostty", f"--title={title}", f"--working-directory={cwd}"]
    if inner_command:
        # Drop back to an interactive shell after the command exits/is
        # interrupted, so the window doesn't just close under you.
        argv += ["-e", "zsh", "-c", f"{inner_command}; exec zsh"]
    return shlex.join(argv)


# ---------------------------------------------------------------- repo shape


def find_repo(name: str) -> Path:
    repo = REPO_ROOT / name
    if not repo.is_dir():
        sys.exit(f"no such repo: {repo}")
    return repo


def list_repos() -> list[str]:
    return sorted(p.name for p in REPO_ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))


def fzf_pick(options: list[str], prompt: str) -> str:
    if not options:
        sys.exit(f"nothing to pick for: {prompt}")
    result = subprocess.run(["fzf", "--prompt", f"{prompt}> "], input="\n".join(options), capture_output=True, text=True)
    choice = result.stdout.strip()
    if not choice:
        sys.exit("nothing selected")
    return choice


def find_activate(repo: Path) -> Path | None:
    for base in (repo, REPO_ROOT):
        for d in ("venv", ".venv"):
            activate = base / d / "bin" / "activate"
            if activate.exists():
                return activate
    return None


def find_manage(repo: Path) -> Path | None:
    candidates = [repo / "manage.py", *repo.glob("*/manage.py")]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def venv_source(repo: Path) -> str | None:
    activate = find_activate(repo)
    return f"source {shlex.quote(str(activate))}" if activate else None


def resolve_window_cmd(repo: Path, pane: str, window: dict) -> str | None:
    """claude, dev/runserver and dev/shell get the repo's venv activated
    first if it has one -- matching the macOS version's `plan()`, which
    applies venv activation to exactly those three, not the others (gitui
    doesn't need Python; editor/nvim isn't run inside the venv either)."""
    name = window["name"]
    source = venv_source(repo)

    if pane == "claude" and name == "claude":
        return f"{source} && claude" if source else "claude"
    if pane == "dev" and name == "runserver":
        manage = find_manage(repo)
        if not manage:
            return source  # no manage.py: still activate the venv if there is one
        run = f"python {shlex.quote(str(manage))} runserver"
        return f"{source} && {run}" if source else run
    if pane == "dev" and name == "shell":
        return source

    return window["cmd"]  # static commands (gitui, editor) or None (plain shell)


# ------------------------------------------------------------------- open


def window_title(title_base: str, pane: str, window_name: str, multi: bool) -> str:
    return f"{title_base}:{pane}:{window_name}" if multi else f"{title_base}:{pane}"


def occupied_numbered_workspaces(clients: list[dict]) -> set[int]:
    used = set()
    prefix = f"{TITLE_PREFIX}:"
    for c in clients:
        title = c["title"] or c["initialTitle"]
        if not title.startswith(prefix):
            continue
        wsid = c["workspace"]["id"]
        if isinstance(wsid, int) and wsid > 0:
            used.add(wsid)
    return used


def allocate_pane_workspace(title_base: str, pane: str, clients: list[dict], reserved: set[int]) -> str:
    """A pane's windows all share one workspace: reuse it if any of the pane's
    windows already exist, otherwise claim the lowest free slot in the pool.

    `reserved` is mutated as slots are claimed -- this run's own prior
    allocations must count as taken immediately, since exec_cmd is async and
    a fresh `hyprctl clients` query right after wouldn't see them yet.
    """
    windows = PANES[pane]
    multi = len(windows) > 1
    for window in windows:
        title = window_title(title_base, pane, window["name"], multi)
        existing = find_by_title(title, clients)
        if existing:
            return str(existing["workspace"]["id"])
    for slot in NUMBERED_WORKSPACE_POOL:
        if slot not in reserved:
            reserved.add(slot)
            return str(slot)
    sys.exit(
        f"no free workspace left for {title_base}:{pane} "
        f"(all of {NUMBERED_WORKSPACE_POOL} are in use -- pack up a repo first)"
    )


def open_pane(repo: Path, title_base: str, pane: str, clients: list[dict], reserved: set[int]) -> bool:
    """Returns True if any window in the pane was newly created (as opposed
    to all of them already existing) -- callers use this to run fixups that
    must only happen once, at creation time."""
    windows = PANES[pane]
    workspace = allocate_pane_workspace(title_base, pane, clients, reserved)
    multi = len(windows) > 1
    created_any = False
    for window in windows:
        title = window_title(title_base, pane, window["name"], multi)
        existing = find_by_title(title, clients)
        if existing:
            focus_address(existing["address"])
            continue
        cmd = resolve_window_cmd(repo, pane, window)
        ghostty_cmd = build_ghostty_cmd(title, repo, cmd)
        exec_cmd(ghostty_cmd, workspace)
        created_any = True
        if multi:
            # dwindle's placement depends on the real mapping order, which
            # can differ from dispatch order if exec_cmd calls fire faster
            # than Ghostty actually starts up -- wait for this one to map
            # before creating the next, so the pane's internal layout (and
            # fixup_dev_layout's assumptions about it) are deterministic.
            wait_for_title(title)
    return created_any


def wait_for_title(title: str, timeout: float = 5.0, interval: float = 0.15) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        c = find_by_title(title)
        if c:
            return c
        time.sleep(interval)
    return None


def fixup_dev_layout(title_base: str) -> None:
    """gitui needs to end up full-height on the right (macOS layout parity:
    runserver top-left, shell bottom-left, gitui right at full height).
    dwindle's outer split deterministically puts the first-opened window
    (gitui, see config.py's PANES ordering) on the left -- flip it with a
    swapsplit layout message. Only call this once, right after the dev
    pane's windows are freshly created: swapsplit is a toggle, so calling it
    again on an already-correct layout would flip it right back.
    """
    title = window_title(title_base, "dev", "gitui", True)
    c = wait_for_title(title)
    if c:
        focus_address(c["address"])
        hypr_dispatch('hl.dsp.layout("swapsplit")')


def desktop_exec(desktop_file: str) -> str:
    path = Path.home() / ".local/share/applications" / f"{desktop_file}.desktop"
    for line in path.read_text().splitlines():
        if line.startswith("Exec="):
            return line[len("Exec=") :]
    raise RuntimeError(f"no Exec= line in {path}")


def open_shared_apps() -> None:
    clients = hypr_clients()
    for key in SHARED_APPS_ORDER:
        app = SHARED_APPS[key]
        existing = find_by_class(app["match_class"], clients)
        if existing:
            if str(existing["workspace"]["id"]) != app["workspace"]:
                move_and_focus(existing["address"], app["workspace"])
            else:
                focus_address(existing["address"])
            continue
        exec_cmd(desktop_exec(app["desktop_file"]))
        address = poll_for_class(app["match_class"])
        if address:
            move_and_focus(address, app["workspace"])
        else:
            print(f"warning: {key} did not appear within the timeout", file=sys.stderr)


def focus_first_pane(title_base: str) -> None:
    """Bring the view to this repo's first pane.

    Named workspaces aren't reachable through the SUPER+1-9/0 bindings (those
    are hard-bound to numbered workspaces only), so without this, opening a
    repo whose window happens to land off-screen -- or re-opening one that's
    already running after you've switched away -- leaves no way back except
    cycling every workspace on the system with SUPER+TAB. Focusing a specific
    window (not the workspace by name) is what reliably switches the visible
    workspace to it.
    """
    first_pane = PANE_ORDER[0]
    windows = PANES[first_pane]
    title = window_title(title_base, first_pane, windows[0]["name"], len(windows) > 1)
    c = wait_for_title(title)
    if c:
        focus_address(c["address"])


def open_repo(repo: Path) -> None:
    title_base = f"{TITLE_PREFIX}:{repo.name}"
    clients = hypr_clients()
    reserved = occupied_numbered_workspaces(clients)
    for pane in PANE_ORDER:
        created = open_pane(repo, title_base, pane, clients, reserved)
        if pane == "dev" and created:
            fixup_dev_layout(title_base)
    open_shared_apps()
    focus_first_pane(title_base)


# ------------------------------------------------------------------- pack


def open_repo_names(clients: list[dict] | None = None) -> list[str]:
    clients = clients if clients is not None else hypr_clients()
    prefix = f"{TITLE_PREFIX}:"
    names = set()
    for c in clients:
        title = c["title"] or c["initialTitle"]
        if title.startswith(prefix):
            rest = title[len(prefix) :]
            names.add(rest.split(":", 1)[0])
    return sorted(names)


def kill_dev_server(repo: Path) -> None:
    repo_real = repo.resolve()
    for proc_dir in Path("/proc").glob("[0-9]*"):
        try:
            cwd = (proc_dir / "cwd").resolve()
            if cwd != repo_real:
                continue
            cmdline = (proc_dir / "cmdline").read_bytes().decode(errors="ignore")
            if "runserver" not in cmdline:
                continue
            os.kill(int(proc_dir.name), signal.SIGTERM)
        except (OSError, ValueError):
            continue


def close_shared_apps() -> None:
    clients = hypr_clients()
    for key in SHARED_APPS_ORDER:
        existing = find_by_class(SHARED_APPS[key]["match_class"], clients)
        if existing:
            close_address(existing["address"])


def close_repo_windows(repo: Path) -> None:
    title_base = f"{TITLE_PREFIX}:{repo.name}"
    clients = hypr_clients()
    for c in clients:
        title = c["title"] or c["initialTitle"]
        if title == title_base or title.startswith(title_base + ":"):
            close_address(c["address"])
    kill_dev_server(repo)


def pack_repo(repo: Path) -> None:
    # Computed before closing: "is any *other* repo currently open",
    # independent of whether `repo` itself was among them (packing a repo
    # that was never open still counts as packing the last one if nothing
    # else is open).
    other_repo_open = any(name != repo.name for name in open_repo_names())
    close_repo_windows(repo)
    if not other_repo_open:
        close_shared_apps()


def pack_all() -> None:
    """Pack every currently open repo, then close the shared apps once at
    the end -- not via pack_repo's own last-repo check in a loop, which
    would race: closing a window is async (hyprctl dispatch returns before
    the app actually unmaps), so a second pack_repo call run immediately
    after the first can still see the just-closed repo's windows and think
    another repo is open. Since pack_all already knows by definition that
    nothing will be left open, it skips that check entirely.
    """
    for name in open_repo_names():
        close_repo_windows(find_repo(name))
    close_shared_apps()


# --------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(prog="launcher.py")
    sub = parser.add_subparsers(dest="action", required=True)

    p_open = sub.add_parser("open", help="open or raise a repo's workspace")
    p_open.add_argument("--repo")

    p_pack = sub.add_parser("pack", help="close a repo's workspace")
    pack_target = p_pack.add_mutually_exclusive_group()
    pack_target.add_argument("--repo")
    pack_target.add_argument("--all", action="store_true", help="close every open repo, and the shared apps with it")

    args = parser.parse_args()

    if args.action == "open":
        repo = find_repo(args.repo) if args.repo else find_repo(fzf_pick(list_repos(), "open"))
        open_repo(repo)
    elif args.action == "pack":
        if args.all:
            pack_all()
        elif args.repo:
            pack_repo(find_repo(args.repo))
        else:
            open_names = open_repo_names()
            pack_repo(find_repo(fzf_pick(open_names, "pack")))


if __name__ == "__main__":
    main()
