# trmrdev — a per-repo workspace in Hyprland/Omarchy.
#
#   make install    packages via `omarchy pkg add`, ~/Work, the trmrdev command
#   make check      what is present and what is missing; changes nothing
#   make clean      nothing to remove; kept so the verb exists
#
# Mirrors ../macos/Makefile's shape (install/check/clean, a manifest loop,
# a non-clobbering symlink step) but not its shell-only constraint: Omarchy
# ships python3 as part of the base system, not as a CLT stub gating
# everything else, so there's no bare-machine bootstrapping problem here.
# The dependency list lives in manifest.txt, not here.

SHELL := /bin/sh
HERE  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

LAUNCHER  := $(HERE)/trmrdev
MANIFEST  := $(HERE)/manifest.txt
LOCAL_BIN := $(HOME)/.local/bin
LINK      := $(LOCAL_BIN)/trmrdev

# Must match config.py's REPO_ROOT -- kept as a literal here rather than
# shelling out to Python at parse time, same tradeoff ../macos/Makefile
# makes with its own hardcoded paths (GHOSTTY_CONF, ZSHRC, NVIM).
REPO_ROOT := $(HOME)/Work

.DEFAULT_GOAL := help
.PHONY: help install check clean link

help:
	@echo 'trmrdev — a per-repo workspace in Hyprland/Omarchy'
	@echo
	@echo '  make install    packages via omarchy pkg add, ~/Work, the trmrdev command'
	@echo '  make check      what is present and what is missing (changes nothing)'
	@echo '  make clean      nothing to remove (no venv, no generated files)'
	@echo '  make link       relink ~/.local/bin/trmrdev (install calls it)'
	@echo
	@echo 'Then: trmrdev open              pick a repo and launch'
	@echo '      trmrdev pack              pick an open repo and close it'
	@echo '      trmrdev pack --all        close every open repo, and the shared apps with it'

# ---------------------------------------------------------------------- check

check:
	@ok=1; \
	if command -v omarchy >/dev/null 2>&1; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' toolchain omarchy "$$(command -v omarchy)"; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' toolchain omarchy 'this installer assumes an Omarchy system'; ok=0; \
	fi; \
	if command -v hyprctl >/dev/null 2>&1; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' toolchain hyprland "$$(command -v hyprctl)"; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' toolchain hyprland 'the launcher drives every window through hyprctl'; ok=0; \
	fi; \
	if command -v python3 >/dev/null 2>&1; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' toolchain python3 "$$(command -v python3)"; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' toolchain python3 'the launcher itself is python3 -- install it by hand'; ok=0; \
	fi; \
	while read -r kind name reason; do \
	  case "$$kind" in ''|\#*) continue;; esac; \
	  pacman -Q "$$name" >/dev/null 2>&1 && s='ok     ' || { s='MISSING'; ok=0; }; \
	  printf '  %s  %-9s %-30s %s\n' "$$s" "$$kind" "$$name" "$$reason"; \
	done < '$(MANIFEST)'; \
	if [ -d '$(REPO_ROOT)' ]; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' extra repo-root '$(REPO_ROOT)'; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' extra repo-root '$(REPO_ROOT) -- where repos are picked from'; ok=0; \
	fi; \
	if [ "$$(readlink '$(LINK)' 2>/dev/null)" = '$(LAUNCHER)' ]; then \
	  printf '  %s  %-9s %-30s %s\n' 'ok     ' config trmrdev '$(LINK)'; \
	else \
	  printf '  %s  %-9s %-30s %s\n' 'MISSING' config trmrdev '$(LINK)'; ok=0; \
	fi; \
	echo; \
	if [ "$$ok" -eq 1 ]; then echo 'all dependencies present'; \
	else echo 'some dependencies missing — run `make install`'; exit 1; fi

# -------------------------------------------------------------------- install

install:
	@command -v omarchy >/dev/null 2>&1 || { echo 'make: `omarchy` not found -- this installer only runs on an Omarchy system' >&2; exit 1; }
	@while read -r kind name reason; do \
	  case "$$kind" in ''|\#*) continue;; esac; \
	  pacman -Q "$$name" >/dev/null 2>&1 && continue; \
	  echo "make: installing $$name — $$reason"; \
	  if [ "$$kind" = aur ]; then omarchy pkg aur add "$$name"; else omarchy pkg add "$$name"; fi; \
	done < '$(MANIFEST)'
	@mkdir -p '$(REPO_ROOT)'
	@$(MAKE) --no-print-directory link
	@echo
	@echo 'make: verifying...'
	@$(MAKE) --no-print-directory check >/dev/null 2>&1 \
	  && echo 'make: done. Run `trmrdev open`.' \
	  || { echo 'make: some things are still missing —' >&2; $(MAKE) --no-print-directory check | grep MISSING >&2; \
	       echo 'make: re-run `make install`, or fix the above by hand.' >&2; exit 1; }

link:
	@mkdir -p '$(LOCAL_BIN)'; \
	if [ -e '$(LINK)' ] && [ ! -L '$(LINK)' ]; then \
	  echo "make: $(LINK) exists and is not a symlink — leaving it alone" >&2; \
	elif [ "$$(readlink '$(LINK)' 2>/dev/null)" = '$(LAUNCHER)' ]; then \
	  :; \
	else \
	  ln -sf '$(LAUNCHER)' '$(LINK)'; echo "make: linked $(LINK)"; \
	fi

clean:
	@echo 'nothing to clean: no venv, no generated files'
