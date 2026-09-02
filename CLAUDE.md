# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
make install    # CLT, Homebrew, packages, ghostty + ~/.zshrc config, the trmrdev symlink; one run is enough
make check      # what is present and what is missing; changes nothing; exits 1 if anything is missing
make clean      # nothing to remove; kept so the verb exists
make ghostty    # ensure macos-option-as-alt in Ghostty's config (install calls it)
make zshrc      # re-splice the ~/.zshrc block (install calls it)
make link       # relink $(brew --prefix)/bin/trmrdev (install calls it)

trmrdev -nu | --no-upgrade      # pick a repo with fzf, launch the workspace
trmrdev -nu --repo X            # skip the picker; X is a name under ~/dev or a full path
trmrdev -u  | --upgrade         # brew upgrade first, then launch
trmrdev -p  | --pack-up         # close a workspace again; pick from the open ones
trmrdev -p  --repo X            # pack up that one
```

`-nu` is a multi-character single-dash option. argparse resolves it by exact
match, so it stays unambiguous even if a `-n` is added later — but it reads
like combined short flags to a human, and it is one character away from `-u`,
which triggers a system-wide `brew upgrade`.

`make install` converges in **one run**: it waits for the Command Line Tools to
finish installing rather than asking to be re-run, and verifies itself with
`make check` at the end instead of assuming it worked.

There is **no test suite, no linter, and no CI** — don't go looking. `make check`
is the only verification the repo has: it probes the toolchain, every
`manifest.txt` entry, Ghostty's config, the `~/.zshrc`
block and the symlink, then exits non-zero on any gap. Run it after touching the
Makefile or the manifest. Beyond that, verification is manual: run `trmrdev
--no-upgrade --repo <something>` and look at the window.

macOS only. Nothing here runs or is meaningfully testable on Linux.

## The shell/Python split

The single most load-bearing decision, and the reason for two languages:

- **`Makefile` is the installer and checker, in POSIX shell**, because it must
  run on a bare Mac where `/usr/bin/make`, `python3` and `git` are all Xcode CLT
  stubs. That machine is precisely the one that needs installing. Do not port
  installer logic to Python — it would be unrunnable exactly when it is needed.
- **`trmrdev.py` is only the launcher.** It installs nothing and checks no
  dependencies. If a change wants to install something from Python, it belongs
  in the Makefile instead. It needs no venv: Ghostty is driven over AppleScript
  through the single `osa()` helper, so there is no third-party module.

## Architecture

Four artifacts, each with one job:

| File | Role |
|---|---|
| `Makefile` | install · check · clean, in shell. The only thing that writes outside the repo. |
| `manifest.txt` | `<kind> <name> <why>` per line. Read by *both* `check` and `install` via the same `while read` loop — adding a dependency means one line here and nothing else. |
| `zshrc-block.zsh` | The managed `~/.zshrc` block, spliced between markers. |
| `trmrdev.py` | The Ghostty launcher. |

There is no venv: AppleScript needs no third-party module, which is why
`make clean` has nothing to remove.

`~/.local/state/trmrdev/workspaces.json` records what each open workspace
started, keyed by repo path: the ids of the tabs created and the apps this tool
launched. It lives outside the repo deliberately — the repo is what gets shared,
and this is machine state.

### trmrdev.py: driving Ghostty

Ghostty exposes **only** AppleScript on macOS — its CLI states outright that
launching the emulator from the command line is unsupported, and there is no
IPC or control socket. Everything goes through `osa()`, in three scripts:
`build()` (one script for the whole workspace), `workspace_tabs()` (find by
working directory) and `close_tabs()`. Two traps, both paid for already:

- **AppleScript references are positional.** Closing `tab 1` renumbers what
  follows, so references collected in an earlier pass point at the wrong tabs.
  `close_tabs()` therefore matches by id and *rescans after every close*;
  collecting first and closing second still closed two tabs of three.
- **`pgrep` cannot see Ghostty** — not by name, not with `-f` against the full
  command line, even when Ghostty is the parent of the shell asking. Detection
  goes through `ps -eo comm` matching the `.app` bundle. Getting this wrong is
  not cosmetic: a false "not running" makes the launcher think it started
  Ghostty, and the build then closes every pre-existing window as startup
  litter.

### trmrdev.py: how the workspace is built

`plan(repo)` returns an ordered `{tab_title: [Pane, ...]}` dict, and **the order
is the geometry** — every split is taken off the tab's first pane, so `gitui`
(`vertical=True`) is listed before `shell` to keep it full-height on the right.
`Pane` assembles one `&&`-joined shell line: `cd`, optional venv activate, title
escape, then `clear` (with `\033[3J` to take the scrollback) before the program,
so the pane opens on its program rather than on the typed plumbing.

Repo shape is probed, not configured: `find_activate` accepts `venv/` or
`.venv/`, `find_manage` looks for `manage.py` at the root or one level down. A
missing `manage.py` degrades the server pane to a plain shell rather than
failing.

### Idempotency is the invariant everywhere

Every write in this repo is designed to be re-runnable, and several of the
non-obvious comments exist because the naive version was wrong:

- **Window reuse**: Ghostty has no user-defined variables, so a workspace is
  recognised by its terminals' **working directory** — the truer fact anyway,
  and it survives a state file that was never written.
- **Fullscreen is a setter, never a toggle.** Exiting and re-entering races
  macOS's animation; the `ctrl-cmd-F` menu shortcut would turn fullscreen *off*
  for the apps already correct. An app already fullscreen on its own Space
  reports no window to System Events (it can only enumerate the active Space) —
  that is the steady state, and it is silently ignored. Ghostty's own
  `toggle_fullscreen` action is likewise a toggle with no readable state, so it
  is only ever applied to a window we just created.
- **`make zshrc`** replaces only what sits between the two markers, backs up
  `~/.zshrc` whenever a byte moves, and appends the block when the markers are
  absent. The `BEGIN_MARK`/`END_MARK` in the Makefile must stay byte-identical
  to the first and last lines of `zshrc-block.zsh`.
- **`make link`** refuses to overwrite a non-symlink; **`make install`** never
  touches an existing `~/.config/nvim`.
- **`--pack-up` closes tabs, never the window.** A workspace can share a window
  with tabs you opened yourself, so closing the window would take them with it.
  If ours were the only tabs, Ghostty closes the emptied window itself.
- **Only apps this tool started are quit**, recorded at open time *before*
  launching anything — that is the one moment "was it already running" is
  knowable. An app you had open is not ours, and even ours stay while another
  workspace is still open.
- **Neither reuse nor pack-up trusts the state file.** Both rediscover our tabs
  by their pinned `titleOverride` (`TAB_TITLES`), so a workspace built by a run
  that died before saving is still reachable. Delete the state file and
  `--pack-up --repo X` still works.
- **The repo's dev servers are ended explicitly** by matching working directory:
  a `manage.py runserver` routinely survives its pane closing and keeps the port.

Edit `zshrc-block.zsh` and re-run `make install` (or `make zshrc`). Never edit
the block inside `~/.zshrc` — the next install overwrites it.

## Working in this codebase

- **The comments are the documentation, and most record a failure already paid
  for.** Do not strip them when editing. Non-obvious examples: `A || B && C`
  associates left in zsh, so the obvious guard idiom sources a file exactly when
  it is already loaded; `DISABLE_AUTO_TITLE` must be exported *within* the pane's
  command line because oh-my-zsh's `termsupport` rewrites titles in `preexec`;
  `ensure_ghostty` strips `CLAUDE*` from the environment handed to `open` so a
  nested `claude` does not inherit `CLAUDE_CODE_CHILD_SESSION` and silently lose
  transcript saving; `glow -s auto` resolves to no-color in a pipe, so previews
  need `-s dark` while `execute()` bindings do not.
- **`DESKTOP_APPS` process names are not derivable** from app names (Firefox
  Developer Edition reports as `firefox`, VS Code as `Code`).
- **Three setup steps cannot be scripted** and the workspace is degraded without
  them: Accessibility permission for whatever app launches `trmrdev` (only the
  companion apps' fullscreen needs it, and it is per launching app — switching
  terminals means granting it again); a Nerd Font set in Ghostty's config. Then
  `p10k configure` once. Report these rather than trying to automate them.
- **`oh-my-zsh` is deliberately not installed by `make install`** — its installer
  rewrites `~/.zshrc` and would destroy the managed block. `install` only warns.
- User-facing errors go through `die()` and name the command to run next; keep
  that shape for new failure paths.
