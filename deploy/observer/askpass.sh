#!/usr/bin/env bash
# GIT_ASKPASS pentru GitHub: git îl cheamă DOAR când serverul cere autentificare (401), cu textul cererii ca argument.
# Tokenul se citește din fișier chiar aici; nu trece prin mediul sau argumentele lui git, nici ale proceselor lui copil.
# Orice altă cerere decât utilizator/parolă e refuzată.
set -euo pipefail
case "${1:-}" in
  Username*) echo "x-access-token" ;;
  Password*) cat -- "${BND_TOKEN_FILE:?}" ;;
  *) exit 1 ;;
esac
