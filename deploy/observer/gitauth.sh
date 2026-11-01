#!/usr/bin/env bash
# Funcție comună `git_net`: autentificare GitHub fără token în URL, în argumentele procesului (ps) sau în ~/.gitconfig.
# Tokenul se citește din $BND_TOKEN_FILE și trece prin variabile de mediu (cere git >= 2.31). Se include cu `source`.
git_net() {
  if [ -n "${BND_TOKEN_FILE:-}" ]; then
    local token
    token="$(cat "$BND_TOKEN_FILE")" || return 90
    GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraheader \
      GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$token" | base64 -w0)" git "$@"
  else
    GIT_TERMINAL_PROMPT=0 git "$@"
  fi
}
