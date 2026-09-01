#!/usr/bin/env bash
# Path translation shared by the hooks. Sourced, never executed.
#
# Claude Code sets CLAUDE_PROJECT_DIR to a NATIVE path. On Windows that is
# `C:\Users\...`, but hooks run under MSYS bash, where `[ -f "C:\Users\..." ]` is
# simply false. A guard that cannot see its own sentinel file fails open while
# looking perfectly configured, so every hook normalizes before testing paths.
#
# cygpath is NOT assumed: it is absent from `C:\Program Files\Git\usr\bin\bash`,
# which is what `shutil.which("bash")` resolves to on a normal Git-for-Windows
# install, so relying on it reintroduces the silent failure it was meant to fix.

# Native (C:\x or C:/x) -> unix (/c/x). Identity on Linux/macOS.
km_to_unix() {
  local p="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$p" 2>/dev/null && return 0
  fi
  p="${p//\\//}"
  case "$p" in
  [A-Za-z]:/*)
    local drive="${p%%:*}"
    local rest="${p#*:}"
    p="/$(printf '%s' "$drive" | tr '[:upper:]' '[:lower:]')${rest}"
    ;;
  esac
  printf '%s' "$p"
}

# Unix (/c/x) -> native (C:/x), for handing a path to a native interpreter.
km_to_native() {
  local p="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$p" 2>/dev/null && return 0
  fi
  case "$p" in
  /[A-Za-z]/*)
    local drive="${p:1:1}"
    p="$(printf '%s' "$drive" | tr '[:lower:]' '[:upper:]'):${p:2}"
    ;;
  esac
  printf '%s' "$p"
}
