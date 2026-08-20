# trmrdev — a per-repo workspace in iTerm2.
#
#   make install    everything: CLT, Homebrew, packages, venv, ~/.zshrc, the command
#   make check      what is present and what is missing; changes nothing
#   make clean      remove the venv
#
# This file is the installer and the checker, in shell, on purpose: it has to
# run on a machine with no Python and no venv — precisely the machine that
# needs installing. Python appears only in what it builds.
#
# On a bare Mac, /usr/bin/make is a stub fronting the Xcode Command Line Tools
# (the same shim as python3 and git), so invoking make at all raises the CLT
# install dialog. Accept it and install waits for it to finish rather than
# asking you to start over: one run is meant to be enough, and it verifies
# itself at the end rather than trusting that it worked.
#
# The dependency list lives in manifest.txt, not here.

SHELL := /bin/sh
HERE  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

VENV       := $(HERE)/venv
LAUNCHER   := $(HERE)/trmrdev.py
BLOCK      := $(HERE)/zshrc-block.zsh
MANIFEST   := $(HERE)/manifest.txt
ZSHRC      := $(HOME)/.zshrc
BEGIN_MARK := \# >>> trmrdev (managed by ~/trmrdev/Makefile) >>>
END_MARK   := \# <<< trmrdev <<<

OMZ        := $(HOME)/.oh-my-zsh
NVIM       := $(HOME)/.config/nvim

# The editor tab opens `nvim +NvimTreeFocus`, so nvim needs a config that
# provides a file tree. NvChad's starter is that config; its .git is dropped
# after cloning so the result is yours to commit, not a fork of a template.
# An existing ~/.config/nvim is never touched.
NVIM_REPO  := https://github.com/NvChad/starter

# Homebrew may be installed but missing from PATH — normal in a fresh shell
# that has not run `brew shellenv`. One line, because a multi-line define
# cannot survive a backslash-continued recipe.
LOAD_BREW := for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$$b" ] && eval "$$($$b shellenv)" && break; done; true

.DEFAULT_GOAL := help
.PHONY: help install check clean venv zshrc link

help:
	@echo 'trmrdev — a per-repo workspace in iTerm2'
	@echo
	@echo '  make install    CLT, Homebrew, packages, venv, ~/.zshrc block, the command'
	@echo '  make check      what is present and what is missing (changes nothing)'
	@echo '  make clean      remove the venv'
	@echo
	@echo 'Then: trmrdev --no-upgrade    pick a repo and launch'
	@echo '      trmrdev --help          every launch option'

# ---------------------------------------------------------------------- check

check:
	@$(LOAD_BREW); \
	miss=0; \
	if xcode-select -p >/dev/null 2>&1; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' toolchain xcode-clt "$$(xcode-select -p)"; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' toolchain xcode-clt 'run: xcode-select --install'; \
	  miss=$$((miss+1)); \
	fi; \
	if command -v brew >/dev/null 2>&1; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' toolchain homebrew "$$(command -v brew)"; \
	  while read -r kind name reason; do \
	    case "$$kind" in ''|\#*) continue;; esac; \
	    if [ "$$kind" = cask ]; then \
	      brew list --cask "$$name" >/dev/null 2>&1 && s='ok     ' || { s='MISSING'; miss=$$((miss+1)); }; \
	    else \
	      brew list --versions "$$name" >/dev/null 2>&1 && s='ok     ' || { s='MISSING'; miss=$$((miss+1)); }; \
	    fi; \
	    printf '  %s  %-9s %-30s %s\n' "$$s" "$$kind" "$$name" "$$reason"; \
	  done < '$(MANIFEST)'; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' toolchain homebrew 'make install will fetch it'; \
	  miss=$$((miss+1)); \
	  echo '  (skipping package checks: nothing to ask)'; \
	fi; \
	for pair in '$(OMZ)|oh-my-zsh|the framework .zshrc is built on' \
	            '$(NVIM)|nvim-config|the NvChad config the editor tab opens'; do \
	  p=$${pair%%|*}; rest=$${pair#*|}; n=$${rest%%|*}; r=$${rest#*|}; \
	  [ -d "$$p" ] && s='ok     ' || { s='MISSING'; miss=$$((miss+1)); }; \
	  printf '  %s  %-9s %-30s %s\n' "$$s" extra "$$n" "$$r"; \
	done; \
	if [ -x '$(VENV)/bin/python' ] && '$(VENV)/bin/python' -c 'import iterm2' 2>/dev/null; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' venv 'venv + iterm2' '$(VENV)'; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' venv 'venv + iterm2' 'the module the launcher drives iTerm2 with'; \
	  miss=$$((miss+1)); \
	fi; \
	if '$(VENV)/bin/python' -c "import ast,sys; m=ast.parse(open(sys.argv[1]).read()); sys.exit(0 if any(isinstance(n,ast.Import) and any(a.name=='iterm2' for a in n.names) for n in ast.walk(m)) else 1)" '$(LAUNCHER)' 2>/dev/null; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' launcher 'imports iterm2' 'trmrdev.py'; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' launcher 'imports iterm2' 'every iterm2 call would be a NameError'; \
	  miss=$$((miss+1)); \
	fi; \
	if grep -qF '$(BEGIN_MARK)' '$(ZSHRC)' 2>/dev/null; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' config zshrc-block '$(ZSHRC)'; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' config zshrc-block '$(ZSHRC)'; miss=$$((miss+1)); \
	fi; \
	link="$$(brew --prefix 2>/dev/null || echo /usr/local)/bin/trmrdev"; \
	if [ "$$(readlink "$$link" 2>/dev/null)" = '$(LAUNCHER)' ]; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' config trmrdev "$$link"; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' config trmrdev "$$link"; miss=$$((miss+1)); \
	fi; \
	echo; \
	if [ "$$miss" -gt 0 ]; then echo "$$miss missing — run \`make install\`"; exit 1; \
	else echo 'all dependencies present'; fi

# -------------------------------------------------------------------- install

install:
	@if ! xcode-select -p >/dev/null 2>&1; then \
	  echo 'make: installing the Xcode Command Line Tools — accept the dialog.'; \
	  xcode-select --install >/dev/null 2>&1 || true; \
	  printf 'make: waiting for it to finish'; \
	  n=0; \
	  while ! xcode-select -p >/dev/null 2>&1; do \
	    n=$$((n+1)); \
	    [ $$n -gt 900 ] && { echo; echo 'make: the Command Line Tools never appeared; install them and re-run' >&2; exit 1; }; \
	    printf '.'; sleep 2; \
	  done; \
	  echo ' done.'; \
	fi
	@$(LOAD_BREW); \
	if ! command -v brew >/dev/null 2>&1; then \
	  echo 'make: installing Homebrew (it will ask for your password)...'; \
	  /bin/bash -c "$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; \
	  $(LOAD_BREW); \
	fi; \
	command -v brew >/dev/null 2>&1 || { echo 'make: Homebrew still not on PATH' >&2; exit 1; }; \
	while read -r kind name reason; do \
	  case "$$kind" in ''|\#*) continue;; esac; \
	  if [ "$$kind" = cask ]; then \
	    brew list --cask "$$name" >/dev/null 2>&1 || { \
	      echo "make: installing $$name — $$reason"; brew install --cask "$$name"; }; \
	  else \
	    brew list --versions "$$name" >/dev/null 2>&1 || { \
	      echo "make: installing $$name — $$reason"; brew install "$$name"; }; \
	  fi; \
	done < '$(MANIFEST)'
	@[ -d '$(OMZ)' ] || echo 'make: oh-my-zsh is missing. Install it by hand — its installer REWRITES ~/.zshrc, which would destroy the managed block.'
	@if [ -d '$(NVIM)' ]; then \
	  echo 'make: ~/.config/nvim already exists, leaving it alone'; \
	else \
	  echo 'make: cloning $(NVIM_REPO) to ~/.config/nvim'; \
	  git clone --depth=1 '$(NVIM_REPO)' '$(NVIM)' \
	    || echo 'make: could not clone the nvim config; the editor tab will open a bare nvim' >&2; \
	  rm -rf '$(NVIM)/.git'; \
	fi
	@$(MAKE) --no-print-directory venv zshrc link
	@echo
	@echo 'make: verifying...'
	@$(MAKE) --no-print-directory check >/dev/null 2>&1 \
	  && echo 'make: done. Run `exec zsh`, then `trmrdev --no-upgrade`.' \
	  || { echo 'make: some things are still missing —' >&2; $(MAKE) --no-print-directory check | grep MISSING >&2; \
	       echo 'make: re-run `make install`, or fix the above by hand.' >&2; exit 1; }

# The venv is the one piece of Python here, and it is an output, never a
# prerequisite: built from brew's interpreter so it survives Xcode changes.
venv:
	@$(LOAD_BREW); \
	py="$$(brew --prefix 2>/dev/null)/bin/python3"; \
	[ -x "$$py" ] || py=python3; \
	if [ ! -x '$(VENV)/bin/python' ]; then \
	  echo "make: building the venv with $$py"; \
	  "$$py" -m venv '$(VENV)'; \
	fi; \
	'$(VENV)/bin/python' -c 'import iterm2' 2>/dev/null || { \
	  echo 'make: installing the iterm2 module'; \
	  '$(VENV)/bin/python' -m pip install -q --upgrade pip; \
	  '$(VENV)/bin/python' -m pip install -q iterm2; }

# Splice the block between its markers, leaving every line around it alone.
# Appends when the markers are absent, and never writes without a backup.
zshrc:
	@if [ -f '$(ZSHRC)' ] && grep -qF '$(BEGIN_MARK)' '$(ZSHRC)'; then \
	  cp '$(ZSHRC)' "$(ZSHRC).trmrdev-$$(date +%Y%m%d-%H%M%S)"; \
	  awk -v blockfile='$(BLOCK)' -v b='$(BEGIN_MARK)' -v e='$(END_MARK)' ' \
	    BEGIN { while ((getline line < blockfile) > 0) block = block line "\n" } \
	    $$0 == b { printf "%s", block; skip = 1; next } \
	    skip && $$0 == e { skip = 0; next } \
	    !skip { print } \
	  ' '$(ZSHRC)' > '$(ZSHRC).new' && mv '$(ZSHRC).new' '$(ZSHRC)'; \
	  echo 'make: refreshed the ~/.zshrc block'; \
	else \
	  [ -f '$(ZSHRC)' ] && cp '$(ZSHRC)' "$(ZSHRC).trmrdev-$$(date +%Y%m%d-%H%M%S)" || true; \
	  printf '\n' >> '$(ZSHRC)'; cat '$(BLOCK)' >> '$(ZSHRC)'; \
	  echo 'make: added the ~/.zshrc block'; \
	fi

link:
	@$(LOAD_BREW); \
	link="$$(brew --prefix 2>/dev/null || echo /usr/local)/bin/trmrdev"; \
	if [ -e "$$link" ] && [ ! -L "$$link" ]; then \
	  echo "make: $$link exists and is not a symlink — leaving it alone" >&2; \
	elif [ "$$(readlink "$$link" 2>/dev/null)" = '$(LAUNCHER)' ]; then \
	  :; \
	else \
	  ln -sf '$(LAUNCHER)' "$$link"; echo "make: linked $$link"; \
	fi

clean:
	@rm -rf '$(VENV)'
	@echo 'removed the venv; `make install` rebuilds it'
