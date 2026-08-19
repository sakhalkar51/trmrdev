# >>> trmrdev (managed by ~/trmrdev/Makefile) >>>
# Rewritten by `make install`. Put your own tweaks OUTSIDE these markers —
# anything between them is replaced.

# Find Homebrew without trusting PATH. Its installer only PRINTS the shellenv
# line to add to ~/.zprofile — it does not add it — so on a fresh machine where
# that step was skipped, brew is installed but invisible to a login shell. Every
# line below would then silently do nothing: no prompt, no completions, no fzf.
# Resolve the prefix by looking, then put its bin on PATH.
if [[ -z $HOMEBREW_PREFIX ]]; then
  for _trmrdev_p in /opt/homebrew /usr/local; do
    [[ -x $_trmrdev_p/bin/brew ]] && export HOMEBREW_PREFIX=$_trmrdev_p && break
  done
  unset _trmrdev_p
fi

if [[ -n $HOMEBREW_PREFIX && ":$PATH:" != *":$HOMEBREW_PREFIX/bin:"* ]]; then
  export PATH="$HOMEBREW_PREFIX/bin:$HOMEBREW_PREFIX/sbin:$PATH"
fi

# zsh's completion system, which nothing here works without: fzf binds tab to
# fzf-completion, and fzf-completion has nothing to complete with until
# compinit has run. oh-my-zsh does this for you, so a .zshrc built on it never
# notices; a .zshrc that is only this block would otherwise get a tab key that
# silently does nothing. Guarded on compdef so it runs at most once.
if ! (( $+functions[compdef] )); then
  autoload -Uz compinit
  compinit -d ${XDG_CACHE_HOME:-$HOME/.cache}/zcompdump-${ZSH_VERSION}
fi

# fzf key bindings and fuzzy completion: ctrl-t files, ctrl-r history,
# alt-c cd, tab completion. After compinit, or the tab binding is inert.
eval "$(fzf --zsh)"

# Global UI. ctrl-e opens the highlighted item in nvim, ctrl-g renders it with
# glow. glow's default `-s auto` is correct here: execute() hands it a real
# terminal, so it picks its style from the background itself.
export FZF_DEFAULT_OPTS="--multi --height 100% --layout=reverse --border \
  --bind 'ctrl-e:execute(echo {} | xargs -r nvim)' \
  --bind 'ctrl-g:execute(echo {} | xargs -r glow -p)' \
  --color=bg+:#313244,bg:#1e1e2e,spinner:#f5e0dc,hl:#f38ba8 \
  --color=fg:#cdd6f4,header:#f38ba8,info:#cba6f7,pointer:#f5e0dc \
  --color=marker:#b4befe,fg+:#cdd6f4,prompt:#cba6f7,hl+:#f38ba8 \
  --color=selected-bg:#45475a"

# fd instead of find: faster, and it honours .gitignore.
export FZF_DEFAULT_COMMAND="fd --strip-cwd-prefix --exclude .git"
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"

# ...including for tab completion, which is a separate mechanism from the
# variables above: fzf calls these two hooks and otherwise falls back to find.
_fzf_compgen_path() { fd --exclude .git . "$1" }
_fzf_compgen_dir()  { fd --type=d --exclude .git . "$1" }

# Smart preview for ctrl-t. Markdown goes to glow rather than bat, so previews
# are rendered instead of syntax-highlighted source. `-s dark` is required here
# and not above: a preview is a pipe, and glow's `auto` style resolves to
# no-color whenever its output is not a terminal. \$FZF_PREVIEW_COLUMNS is
# escaped so it reaches the preview process instead of expanding to nothing at
# export time.
export FZF_CTRL_T_OPTS="--preview 'if [ -d {} ]; then eza --tree --level=2 --color=always --icons {} | head -200; else case {} in *.md|*.markdown) glow -s dark -w \$FZF_PREVIEW_COLUMNS -- {} ;; *) bat --style=numbers --color=always --line-range :500 {} ;; esac; fi'"

# alt-c directory preview.
export FZF_ALT_C_COMMAND="fd --type=d --strip-cwd-prefix --exclude .git"
export FZF_ALT_C_OPTS="--preview 'eza --tree --level=2 --color=always --icons {} | head -200'"

# Wiring for the shell packages the manifest installs. Installing them puts
# files on disk and nothing more — each has to be sourced to exist. `p10k` in
# particular is a shell function, not a binary, which is why `brew list` can
# call powerlevel10k installed while `p10k configure` reports no such command.
#
# Every source is guarded, so this block is safe to add to a .zshrc that
# already loads any of them by hand: the guard sees it loaded and skips.

# Written as full `if` blocks rather than `guard || test && source`: in zsh
# those operators share precedence and associate left, so `A || B && C` is
# `(A || B) && C` — which sources the file precisely when the guard says it is
# already loaded. Exactly backwards, and silent.
_trmrdev_load() {
  local guard=$1 file=$2
  (( $+functions[$guard] )) && return 0
  [[ -r $file ]] || return 0
  source $file
}

if [[ -n $HOMEBREW_PREFIX ]]; then
  # powerlevel10k. Sourced after oh-my-zsh has run — which it has, since this
  # block goes at the end — so nothing overwrites the prompt afterwards.
  # Run `p10k configure` once to generate ~/.p10k.zsh; it appends its own
  # source line for that config, so this block does not.
  _trmrdev_load p10k \
    $HOMEBREW_PREFIX/share/powerlevel10k/powerlevel10k.zsh-theme

  _trmrdev_load _zsh_autosuggest_start \
    $HOMEBREW_PREFIX/share/zsh-autosuggestions/zsh-autosuggestions.zsh

  # Syntax highlighting must be sourced last of all — its own docs are explicit
  # about it, because it wraps widgets defined before it.
  _trmrdev_load _zsh_highlight \
    $HOMEBREW_PREFIX/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

unset -f _trmrdev_load

# The aliases the manifest installs eza, bat and neovim for. Aliases are
# interactive-only, so scripts still get the real ls/cat. Delete the line if
# you would rather keep the originals.
alias ls='eza'
alias cat='bat'
alias vi='nvim'

# What mysql-client and pkgconf are here for: building Python's mysqlclient
# against Homebrew's MySQL. Guarded on the .pc file, because an unguarded
# pkg-config call for a package that is not installed prints an error on every
# single shell startup.
if [[ -n $HOMEBREW_PREFIX && -r $HOMEBREW_PREFIX/opt/mysql-client/lib/pkgconfig/mysqlclient.pc ]]; then
  export PKG_CONFIG_PATH="$HOMEBREW_PREFIX/opt/mysql-client/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
  export MYSQLCLIENT_LDFLAGS="$(pkg-config --libs mysqlclient)"
  export MYSQLCLIENT_CFLAGS="$(pkg-config --cflags mysqlclient)"
fi

# <<< trmrdev <<<
