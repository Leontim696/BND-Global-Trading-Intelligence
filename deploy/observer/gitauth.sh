#!/usr/bin/env bash
# Funcția comună `git_net`: autentificare GitHub prin GIT_ASKPASS (askpass.sh), cu privilegii minime. Se include cu `source`.
#
# De ce nu `http.extraheader` prin GIT_CONFIG_VALUE_0 (varianta din #227): variabilele de mediu ale unui proces sunt
# citibile de același utilizator și de root din /proc/<pid>/environ și se moștenesc în TOATE procesele copil ale lui git
# (git-remote-https, eventuale hook-uri). Cu GIT_ASKPASS, tokenul nu e nici în mediul, nici în argumentele lui git:
# îl citește doar helperul askpass, scurt, din fișier. Helperul `credential.helper` e dezactivat pentru acest apel (altfel
# `credential approve` ar putea salva tokenul în ~/.git-credentials). Tokenul vine din $BND_TOKEN_FILE sau, dacă
# există, din credențialul systemd ($CREDENTIALS_DIRECTORY/github-token), caz în care utilizatorul serviciului nici
# măcar nu trebuie să poată citi fișierul din /etc.
_gitauth_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
git_token_file() {
  if [ -n "${BND_TOKEN_FILE:-}" ]; then printf '%s' "$BND_TOKEN_FILE"
  elif [ -n "${CREDENTIALS_DIRECTORY:-}" ] && [ -e "$CREDENTIALS_DIRECTORY/github-token" ]; then printf '%s' "$CREDENTIALS_DIRECTORY/github-token"
  fi
}
git_net() {
  local tokfile
  tokfile="$(git_token_file)"
  if [ -n "$tokfile" ]; then
    [ -r "$tokfile" ] || return 90
    BND_TOKEN_FILE="$tokfile" GIT_ASKPASS="$_gitauth_dir/askpass.sh" GIT_TERMINAL_PROMPT=0 \
      GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0='' git "$@"
  else
    GIT_TERMINAL_PROMPT=0 git "$@"
  fi
}
