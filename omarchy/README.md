# trmrdev — Omarchy/Hyprland port

A per-repo dev workspace for Hyprland/Omarchy, built to the same idea as
[`../macos`](../macos): pick a repo, get a window set. The implementation is
different because the platform is: no AppleScript, no Homebrew, no macOS
Spaces.

## What's different from the macOS version

- Repos live under `~/Work`, not `~/dev`.
- No VS Code.
- Browser is Chromium (the system default), and it's not a raw window this
  tool drives — the repo's local dev server is an Omarchy web app
  (`omarchy webapp install`), launched/focused like any other app.
- Ghostty *tabs* are replaced by separate Ghostty *windows*, each pinned to a
  per-repo named Hyprland workspace via `windowrulev2`, identified by a
  `trmrdev:<repo>:<pane>` window title instead of Ghostty's `titleOverride`.
- The macOS version's "dev" tab (runserver / shell / gitui as one tab with
  splits) becomes three separate tiled windows here, not Ghostty splits.

## Layout

Per repo, 3 panes, 5 windows total:

| Pane | Windows |
|---|---|
| `claude` | `claude` |
| `dev` | `runserver`, `shell`, `gitui` (tiled) |
| `editor` | `nvim +Neotree` |

Every window is titled `trmrdev:<repo>:<pane>[:<window>]`, which is how the
launcher finds its own windows again for raise/pack-up without trusting a
state file — same idea as the macOS version's `TAB_TITLES`, different
mechanism (Hyprland window titles vs. Ghostty tab titles).

Panes live on **numbered** workspaces (`config.NUMBERED_WORKSPACE_POOL`, 1-6),
not named ones. First attempt used named workspaces (`trmrdev:<repo>:<pane>`)
so any number of repos could each get their own without colliding — but
Omarchy's default SUPER+1-9/0 bindings switch to a specific numbered
workspace ID and never traverse named ones, so those workspaces were
completely unreachable by hand once you switched away. Each pane now claims
the lowest free slot in the pool (reused if that pane already has a window
open) and gives it back when packed up. This caps concurrent repos at
`len(pool) // 3` (2, with the default pool of 6) — a real tradeoff, but the
workspaces are actually usable, which the named-workspace version wasn't.
Workspaces 7-10 are carved out for the shared apps below, not available to
repo panes.

Venv activation matches the macOS version's `plan()` exactly: `claude`,
`dev/runserver`, and `dev/shell` source the venv first if one exists;
`dev/gitui` and `editor` don't (gitui and nvim don't need it). `runserver`
additionally runs `manage.py runserver` if the repo has one (root or one
level down) -- without it, the pane is still venv-activated, just sitting at
a plain prompt. `find_activate` checks `<repo>/venv` and `<repo>/.venv`
first, then falls back to the same two names directly under `REPO_ROOT`
(`~/Work/venv`) -- a venv doesn't have to live inside each repo.

Apple Music, GitHub, Slack, and the local dev server (the "Django Dev"
Omarchy web app) are **not** part of any repo's 3 workspaces — they're shared
across every repo, pinned to fixed workspace IDs (7, 8, 9, 10 respectively)
so they're always in the same place, launched/focused (never duplicated)
every time `open` runs. They never carry a `trmrdev:` title, so `pack`'s
window-matching loop (which matches on that prefix) never touches them
directly while another repo is still open — `pack` on one of two open repos
only closes that repo's own windows.

Packing up the **last** open repo also closes the shared apps: `pack_repo`
checks `open_repo_names()` against every repo *other* than the one being
packed, and if none remain, calls `close_shared_apps()` (matched by window
class, same as `open_shared_apps()`) right after closing that repo's own
windows. So the shared apps track whether any repo workspace is active at
all, not any one repo's lifecycle.

`pack --all` closes every open repo instead of picking one, then closes the
shared apps once at the end -- not by calling `pack_repo` in a loop, which
would race: closing a window is async (`hyprctl dispatch` returns before the
app actually unmaps), so a `pack_repo` call run immediately after another can
still see the just-closed repo's windows and wrongly conclude another repo
is open. `pack_all` shares `close_repo_windows()` with `pack_repo` but skips
its last-repo check entirely, since packing everything already guarantees
nothing will be left open.

## Dual-monitor layout

`~/.config/hypr/workspaces.lua` (Hyprland config, not part of this launcher)
pins workspaces 1-3 to `HDMI-A-2` (primary, physically on the right) and 4-10
to `HDMI-A-3` (secondary, physically on the left) via `hl.workspace_rule`.
That keeps every repo pane on the primary display and pushes all four shared
apps to the secondary one whenever both monitors are connected. On a single
display, the rules for the disconnected monitor simply don't apply — nothing
here needs to change when you unplug the second monitor, and this launcher
has no monitor-awareness of its own.

The `dev` pane's internal layout (runserver top-left, shell bottom-left,
gitui right at full height) needs its 3 windows created one at a time,
waiting for each to actually map before opening the next: dwindle's tiling
placement depends on real creation order, and firing all 3 `exec_cmd` calls
back-to-back can let Ghostty's startup time reorder that vs. dispatch order.
Skipping the wait produced a wrong, non-reproducible layout in testing.

## Install

```sh
cd omarchy
make check     # what's present and what's missing; changes nothing
make install   # packages via `omarchy pkg add` (manifest.txt), ~/Work, the trmrdev command
```

Mirrors [`../macos/Makefile`](../macos/Makefile)'s install/check/clean shape,
but not its shell-only constraint -- Omarchy ships python3 as part of the
base system rather than gating it behind a Command Line Tools install, so
there's no bare-machine bootstrapping problem to design around here. `make
install` ends by symlinking `omarchy/trmrdev` onto `~/.local/bin/trmrdev`
(never clobbering a pre-existing non-symlink there) so it runs as a bare
command from anywhere, not just `cd omarchy && python3 launcher.py`. The
symlink target is a small shell wrapper, not `launcher.py` directly --
Python sets `sys.path[0]` from the invoked path, and a plain symlink to
`launcher.py` would point that at `~/.local/bin` instead of `omarchy/`,
breaking `from config import ...`.

## Usage

```sh
trmrdev open                  # fzf-pick a repo under ~/Work
trmrdev open --repo NAME      # skip the picker
trmrdev pack                  # fzf-pick from currently open repos
trmrdev pack --repo NAME      # skip the picker
trmrdev pack --all            # close every open repo, and the shared apps with it
```

Without `make install`, run the same subcommands as `python3 launcher.py
<subcommand>` from inside `omarchy/`.

No package-upgrade step (the macOS version's `-u`/`brew upgrade` before
open) — removed on request.

Order of panes/apps is config, not code — edit `config.py`'s `PANE_ORDER` /
`SHARED_APPS_ORDER` (or ask Claude to) to change what opens and in what
sequence.

Named workspaces aren't reachable through the SUPER+1-9/0 bindings (those are
hard-bound to numbered workspaces only) — the only default way to reach one
otherwise is cycling every workspace on the system with SUPER+TAB. So `open`
always ends by focusing the first pane's window, which switches the visible
workspace to it. This makes `open` doubly useful on an already-open repo:
since it's idempotent (existing windows are focused, not duplicated), running
it again after you've switched away is how you get back.

## Menu

Wired into the Omarchy Super+Space menu
(`~/.config/omarchy/extensions/omarchy-menu.jsonc`) as two entries, each
running in a throwaway floating terminal:
- **Trmrdev Setup** — `open`
- **Trmrdev Packup** — `pack`

## Status

Tested end-to-end against two real repos (a Django app and a non-Django
repo), including both open concurrently — open, pack-up, the
manage.py-fallback path, focus-back-on-reopen, numbered-workspace pool
sharing across repos, the `dev` pane's internal layout (reproducible across
repeated open/pack/open cycles on both repos), and that `pack` never touches
the shared web apps, all verified working with no collisions. Not yet
tested: the dev-server-survives-pane-close safety net (`kill_dev_server` in
launcher.py) against an actual running `runserver` process, since neither
test repo had its Python deps installed.
