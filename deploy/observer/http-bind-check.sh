#!/usr/bin/env bash
# ExecStartPre pentru bnd-observer-http: refuză adrese de ascultare nesigure. http.server nu are autentificare.
set -euo pipefail
bind="${BND_HTTP_BIND:-}"   # gol/nesetat => systemd ar lăsa --bind gol = toate interfețele: refuzat
case "$bind" in
  127.0.0.1|::1|localhost) exit 0 ;;
  0.0.0.0|::|"") echo "REFUZ: BND_HTTP_BIND=$bind ascultă pe toate interfețele." >&2; exit 1 ;;
esac
[ "${BND_HTTP_ALLOW_NON_LOOPBACK:-}" = "yes" ] || {
  echo "REFUZ: BND_HTTP_BIND=$bind nu e loopback. Leagă-l doar de o interfață VPN (WireGuard/Tailscale) sau pune un proxy, apoi setează BND_HTTP_ALLOW_NON_LOOPBACK=yes și o regulă de firewall pentru IP-ul Home Assistant." >&2
  exit 1; }
echo "Atenție: ascult pe $bind (non-loopback) cu confirmare explicită; verifică firewall-ul."
