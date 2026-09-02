# nvim overlay

LazyVim configuration, laid over the upstream [LazyVim starter](https://github.com/LazyVim/starter)
that `make install` clones.

Four of these files are taken verbatim from [Omarchy](https://github.com/omacom/omarchy)
(MIT), from `config/nvim` at commit `7c273f49` — the last before Omarchy moved
its Neovim config out into a separate `omarchy-nvim` package:

| File | What it does |
|---|---|
| `lazyvim.json` | Enables the `editor.neo-tree` LazyExtra, so there is a real file tree rather than the snacks explorer |
| `lua/plugins/all-themes.lua` | Loads eleven colourschemes lazily so any can be switched to |
| `lua/plugins/omarchy-theme-hotreload.lua` | Reloads the colourscheme when `plugins/theme.lua` changes |
| `lua/plugins/snacks-animated-scrolling-off.lua` | Turns off snacks' scroll animation |
| `plugin/after/transparency.lua` | Clears background highlights so the terminal shows through |

`lua/plugins/theme.lua` is **not** from Omarchy. There, that file is generated
at runtime by the OS-wide theme switcher, so it is absent from their repo and
the hot-reload above would have nothing to require. It is pinned here to
catppuccin-mocha, matching the shell, fzf and p10k on this machine.
