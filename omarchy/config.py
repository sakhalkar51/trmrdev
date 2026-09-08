"""Editable configuration for the Omarchy trmrdev workspace launcher.

Edit PANE_ORDER to change which panes open and in what order for every repo.
Edit PANES to change what's inside a pane. Edit SHARED_APPS_ORDER/SHARED_APPS
for the cross-repo apps (Slack, browser) that aren't tied to any one repo.
This file is the intended place to hand-edit or ask Claude to edit -- the
launcher only ever reads it, never writes it.
"""

from pathlib import Path

REPO_ROOT = Path.home() / "Work"

# Each pane is one named Hyprland workspace (trmrdev:<repo>:<pane>). A pane
# with more than one window tiles them on that workspace -- this is where the
# macOS version's "dev" tab split (runserver/shell/gitui) lives now, as three
# separate windows instead of Ghostty splits.
#
# "cmd": None means the launcher resolves the command at runtime (see
# launcher.py's resolve_window_cmd) -- used for things that depend on the
# repo's own shape, like whether manage.py or a venv exists.
PANE_ORDER = ["claude", "dev", "editor"]

PANES = {
    "claude": [
        # cmd resolved at runtime: venv gets activated first if the repo has
        # one, then `claude` runs (matches the macOS version's "claude" pane).
        {"name": "claude", "cmd": None},
    ],
    "dev": [
        # Open order: gitui first so it's the lone window in dwindle's outer
        # split, runserver/shell second/third so they cluster in the other
        # half (runserver on top since it's opened before shell). The outer
        # split itself always puts the first-opened window on the left
        # (dwindle:force_split=2 on this system, deterministic, not
        # cursor-based) -- launcher.py flips it with a "swapsplit" layout
        # message afterward to put gitui on the right, matching the macOS
        # version's layout.
        {"name": "gitui", "cmd": "gitui"},
        {"name": "runserver", "cmd": None},
        {"name": "shell", "cmd": None},
    ],
    "editor": [
        {"name": "editor", "cmd": "nvim +Neotree"},
    ],
}

# Apps shared across every repo: one instance each, never duplicated per
# repo, always moved back to the same workspace ID so they're in the same
# place every time. `match_class` was found by actually launching each app
# once and reading its window class off `hyprctl clients -j` -- Chromium
# app-mode windows fork through setsid/uwsm-app, so a window-open rule can't
# reliably target their workspace; the launcher instead launches, polls for
# the class to appear, then explicitly moves it.
SHARED_APPS_ORDER = ["apple_music", "github", "slack", "browser"]

SHARED_APPS = {
    "apple_music": {
        "workspace": "7",
        "match_class": "chrome-music.apple.com__in_-Default",
        "desktop_file": "Apple Music",
    },
    "github": {
        "workspace": "8",
        "match_class": "chrome-github.com__-Default",
        "desktop_file": "GitHub",
    },
    "slack": {
        "workspace": "9",
        "match_class": "chrome-app.slack.com__client_T029VAHB475-Default",
        "desktop_file": "Slack",
    },
    "browser": {
        "workspace": "10",
        "match_class": "chrome-localhost__-Default",
        "desktop_file": "Django Dev",
    },
}

# Numbered workspaces for repo panes -- SUPER+1-9/0 in Omarchy's default
# bindings only ever switches to a specific numbered workspace ID, never a
# named one, so a pane has to live on one of these to be reachable that way.
# 7-10 are reserved for the shared apps above; a repo's panes claim whichever
# of these are free and give them back when packed up.
NUMBERED_WORKSPACE_POOL = list(range(1, 7))

TITLE_PREFIX = "trmrdev"
