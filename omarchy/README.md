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

Panes live on **numbered** workspaces (`config.NUMBERED_WORKSPACE_POOL`, 1-8),
not named ones. First attempt used named workspaces (`trmrdev:<repo>:<pane>`)
so any number of repos could each get their own without colliding — but
Omarchy's default SUPER+1-9/0 bindings switch to a specific numbered
workspace ID and never traverse named ones, so those workspaces were
completely unreachable by hand once you switched away. Each pane now claims
the lowest free slot in the pool (reused if that pane already has a window
open) and gives it back when packed up. This caps concurrent repos at
`len(pool) // 3` (2, with the default pool of 8) — a real tradeoff, but the
workspaces are actually usable, which the named-workspace version wasn't.

Venv activation matches the macOS version's `plan()` exactly: `claude`,
`dev/runserver`, and `dev/shell` source the venv first if one exists;
`dev/gitui` and `editor` don't (gitui and nvim don't need it). `runserver`
additionally runs `manage.py runserver` if the repo has one (root or one
level down) -- without it, the pane is still venv-activated, just sitting at
a plain prompt. `find_activate` checks `<repo>/venv` and `<repo>/.venv`
first, then falls back to the same two names directly under `REPO_ROOT`
(`~/Work/venv`) -- a venv doesn't have to live inside each repo.

Slack and the local dev server (the "Django Dev" Omarchy web app, opened
earlier) are **not** part of any repo's 3 workspaces — they're shared across
every repo, pinned to fixed workspace IDs (9 and 10) so they're always in the
same place, launched/focused (never duplicated) every time `open` runs. Since
they never carry a `trmrdev:` title, `pack` (which matches on that prefix)
never touches them either — packing up a repo only closes that repo's own
windows.

The `dev` pane's internal layout (runserver top-left, shell bottom-left,
gitui right at full height) needs its 3 windows created one at a time,
waiting for each to actually map before opening the next: dwindle's tiling
placement depends on real creation order, and firing all 3 `exec_cmd` calls
back-to-back can let Ghostty's startup time reorder that vs. dispatch order.
Skipping the wait produced a wrong, non-reproducible layout in testing.

## Usage

```sh
cd omarchy
python3 launcher.py open                  # fzf-pick a repo under ~/Work
python3 launcher.py open --repo NAME      # skip the picker
python3 launcher.py pack                  # fzf-pick from currently open repos
python3 launcher.py pack --repo NAME      # skip the picker
```

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
