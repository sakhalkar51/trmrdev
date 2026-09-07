# themes

Catppuccin Mocha, everywhere the workspace reaches.

Most of it is handled by `make install`: Ghostty and bat ship the palette
built in and only need selecting, `eza-theme.yml` here is copied to
`~/.config/eza/theme.yml`, and nvim, fzf, gitui, VS Code, powerlevel10k and
zsh-syntax-highlighting were already Mocha.

## The two that cannot be scripted

Slack and Firefox both apply themes through their own UI, with no config file
to write. They are recorded here so the setup is at least reproducible by
instruction.

### Slack

Preferences → Themes → Custom Theme, and paste:

```
#1E1E2E,#F8F8FA,#CBA6F7,#1E1E2E,#11111B,#CDD6F4,#CBA6F7,#EBA0AC,#1E1E2E,#CDD6F4
```

Two limits, both Slack's rather than the theme's:

**The string only reaches the sidebar and top nav.** All ten slots map there —
column background, active and hover items, text, mention badge, top nav — and
none of them touches the message pane. Catppuccin's own template gives it away:
the Latte entry is annotated *"Make sure to enable light mode!"*, because the
message pane follows Slack's **Appearance** setting, not the string. So the
message area has exactly two states, Slack's light and Slack's dark, and Mocha
pairs with dark. It will read as *a* dark, close to but not equal to
`#1E1E2E`; nothing in a theme string can close that gap. Only injecting CSS
into Slack's Electron bundle would, which breaks on every update.

**The redesign remaps the values.** Slack maps the string onto its own built-in
colours rather than applying the palette literally — on this machine the
applied theme recorded a titlebar of `#121016`, which is neither base nor
crust. Catppuccin say as much upstream; on older Slack builds it applies
exactly.

### Firefox Developer Edition

Catppuccin ships Firefox as a [Firefox Color](https://addons.mozilla.org/en-GB/firefox/addon/firefox-color/)
configuration, not an add-on that can be force-installed, so it takes two
clicks:

1. Install Firefox Color from AMO.
2. Open this link and apply it — Mocha, mauve accent, matching the rest:

```
https://color.firefox.com/?theme=XQAAAAJEBAAAAAAAAABBqYhm849SCicxcUcPX38oKRicm6da8pFtMcajvXaAE3RJ0F_F447xQs-L1kFlGgDKq4IIvWciiy4upusW7OvXIRinrLrwLvjXB37kvhN5ElayHo02fx3o8RrDShIhRpNiQMOdww5V2sCMLAfehhpkvCNGPFQ9qpGpx7BgGSYPGUMFXC1Ua9FaxHdWOc93hEJrTCm7pTY2gENlkIGOUk-0q5koU7B1u0Ej-oMph40xEOeck_YUJD52Bwer09STdlto8FTe2opihD2FyRdpJyZydtlY3dK_RO373JUB4GPAs2saJone2-92ozhdZDXTzFe1BzECDYiTLKw8wgkHlYGBfEaHwiRhB6Xx67wrqMSr8VhLm8d-NCA1DySJVtxxWJN-qabWQpDds2gw6dhs97Ngt5Z_6ZhJ5vv31xfjj2v6iK816VOdJaIaQu4xsqHAytxXRLJQ8LtmF0BsXZI5kUVsRJUHALGJAvl388n-yyQfaq8ZWzVK-rrBoAJJqwlvJaa-7K1eFh6NaMojpf5pl-eqKMtg1KMmYlS4DjK6Z__leZhs
```

## Claude Code

There is no Catppuccin theme for Claude Code, and it does not need one. Set
its theme to `dark-ansi` — the binary labels that *"Dark mode (ANSI colors
only)"* — and it draws from the terminal's sixteen ANSI colours, which Ghostty
now supplies as Catppuccin Mocha. The trade is fewer colours than the default
`dark` theme, which uses truecolor.

Set it with `/config` inside Claude Code, or in `~/.claude/settings.json`:

```json
{ "theme": "dark-ansi" }
```

`make install` deliberately leaves this alone. The other themed files are ones
this repo owns or writes wholesale; `~/.claude/settings.json` is another tool's
state, holding keys that have nothing to do with the workspace, and quietly
rewriting it on every install is a good way to lose them to a schema change.

## glow

Still unthemed. Catppuccin publishes only a whiskers template for glow
(`catppuccin/glamour` contains `glamour.tera` and nothing built), so there is
no style file to vendor. Previews use glow's built-in dark.
