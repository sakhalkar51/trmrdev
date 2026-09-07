# trmrdev

A per-repo development workspace in Ghostty. Pick a repo, get a window:

| Tab | Contents |
|---|---|
| `claude` | claude, in the repo root |
| `dev` | runserver top-left, shell bottom-left, gitui right at full height |
| `editor` | nvim with the file-tree sidebar focused |

Plus VS Code opened on the repo, Firefox and Slack, each fullscreen on its own
Space. Running it twice for the same repo raises that workspace rather than
building a second one.

macOS only, and Homebrew-based.

## Install

```sh
cd trmrdev
make install
```

On a machine with nothing on it, `/usr/bin/make` is a stub fronting the Xcode
Command Line Tools, so `make install` raises the CLT dialog. Accept it and the
install waits rather than asking you to start over — from there it installs
Homebrew, every package, Ghostty's config, the `~/.zshrc` block and the
`trmrdev` command, then verifies itself.

Ghostty is driven over AppleScript, so there is no venv and no third-party
Python module to install.

```sh
exec zsh          # pick up the shell config
trmrdev -nu       # pick a repo with fzf and launch
```

| Command | Does |
|---|---|
| `make install` | everything; one run is enough, and it verifies itself |
| `make check` | what is present and what is missing; changes nothing |
| `make clean` | nothing to remove — there is no build output |
| `trmrdev` | the quick help |
| `trmrdev -nu` | pick a repo and open its workspace (`--no-upgrade`) |
| `trmrdev -u` | `brew upgrade` first, then open (`--upgrade`) |
| `trmrdev -p` | pack one up again; pick from what is open (`--pack-up`) |
| `trmrdev -p --repo zeus` | pack up that one |
| `trmrdev --help` | every launch option |

Opening and packing up are both idempotent. Opening a repo that is already
open raises it rather than building a second copy; packing up one that is
already packed up says so and changes nothing.

Packing up closes **only the tabs trmrdev created** — the window and any tab
you opened yourself stay exactly as they were. It also ends the dev servers
running in that repo, which outlive their pane often enough to matter, and
quits the apps *it* started. An app you already had open is not its to close,
and it stays put while any other workspace is still open.

## Three things you must do by hand

None can be scripted, and the workspace is degraded without them.

1. **Grant Accessibility** to whichever app you launch `trmrdev` from (Ghostty,
   Terminal, Shortcuts) in System Settings → Privacy & Security → Accessibility.
   Only the *companion apps'* fullscreen depends on it — the workspace itself
   works regardless. macOS exposes native fullscreen solely as an accessibility
   attribute, so nothing can reach it another way. The permission is per
   launching app: switching terminals means granting it again.
2. **Theme Slack and Firefox** — both apply themes through their own UI, with
   no config file to write. `themes/README.md` has the Slack colour string and
   the Firefox Color link, both Mocha. Everything else is themed by
   `make install`.
3. **Set the terminal font** to JetBrainsMono Nerd Font (or Fira Code Nerd
   Font) in Ghostty's config (`font-family = "JetBrainsMono Nerd Font"`).
   `make install` installs the fonts, but nothing can select one for you —
   until you do, the prompt and `eza --icons` render as tofu boxes.

Then run **`p10k configure`** once to build your prompt. The block sources
powerlevel10k, but the theme's own settings live in `~/.p10k.zsh`, which only
that wizard writes.

`oh-my-zsh` is deliberately not installed for you: its installer **rewrites
`~/.zshrc`**, which would destroy the managed block. `make install` tells you
if it is missing.

## What it assumes

- Your repos live in `~/dev`. Each workspace is one directory under it.
- A repo's virtualenv is `venv/` or `.venv/` at its root, and is *activated*,
  never created — so each repo keeps the interpreter it was built with.
- `manage.py` sits at the repo root or one level down. Found, it becomes the
  runserver pane; absent, that pane is just a shell.
- nvim has a config providing a file tree. If `~/.config/nvim` is missing,
  `make install` clones NvChad's starter there and drops its `.git`, so the
  result is yours to commit. An existing config is never touched.

## Making it yours

`manifest.txt` is the dependency list — one `<kind> <name> <why>` per line.
It is opinionated: it installs the prompt, shell plugins and applications this
setup is built around. Delete the lines you do not want before `make install`.

`zshrc-block.zsh` is spliced into `~/.zshrc` between markers on every install.
Edit it there, not in `~/.zshrc` — anything between the markers is replaced.
Everything outside them is left alone, and a backup is taken whenever a byte
moves.

## Layout

```
Makefile          install · check · clean, in shell
manifest.txt      the dependency list
zshrc-block.zsh   the managed ~/.zshrc block
trmrdev.py        the launcher
(no venv — AppleScript needs no third-party module)
```

The installer is shell rather than Python on purpose: it has to run on a
machine that has neither, which is exactly the machine that needs installing.
