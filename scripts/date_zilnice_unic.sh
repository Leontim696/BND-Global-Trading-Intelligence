#!/usr/bin/env bash
# Lumânările zilnice pentru TOT universul „unic” (100 de piețe), din aceleași surse ca formatii-ai.yml:
# ETF/forex/mărfuri și crypto Yahoo, monedele Binance, apărarea și acțiunile. Folosit de bucla intraday (P26), care
# avea înainte doar date-piete (57 de piețe). O sursă căzută nu le oprește pe celelalte.
#   date_zilnice_unic.sh DOSAR [AAAA-LL-ZZ]
set -uo pipefail
out="$1"; start="${2:-$(date -u -d '-1 year' +%Y-%m-%d)}"
mkdir -p "$out"
names="$(python -c "from src.bnd.universe import UNIVERSES; print(','.join(m.name for m in UNIVERSES['unic']))")"
groups="$(python -m src.bnd.crypto50 --split "$names")"
pick() { echo "$groups" | sed -n "s/^$1=//p"; }
etf="$(pick etf)"; yahoo_crypto="$(pick yahoo_crypto)"; binance="$(pick binance)"; defense="$(pick defense)"; stocks="$(pick stocks)"
[ -n "$etf" ] && { python -m src.bnd.backtest_cli fetch-universe --universe etf --markets "$etf" --start "$start" --out-dir "$out" > /dev/null || echo "::warning::date zilnice ETF incomplete"; }
[ -n "$yahoo_crypto" ] && { python -m src.bnd.backtest_cli fetch-universe --universe crypto --markets "$yahoo_crypto" --start "$start" --out-dir "$out" > /dev/null || echo "::warning::date zilnice crypto Yahoo incomplete"; }
[ -n "$binance" ] && { python -m src.bnd.crypto50 --out "$out" --only "$binance" > /dev/null || echo "::warning::date zilnice Binance incomplete"; }
[ -n "$defense" ] && { python -m src.bnd.backtest_cli fetch-universe --universe defense --markets "$defense" --start "$start" --out-dir "$out" > /dev/null || echo "::warning::date zilnice apărare incomplete"; }
[ -n "$stocks" ] && { python -m src.bnd.backtest_cli fetch-universe --universe stocks --markets "$stocks" --start "$start" --out-dir "$out" > /dev/null || echo "::warning::date zilnice acțiuni incomplete"; }
echo "date zilnice: $(find "$out" -name '*.csv' | wc -l) fișiere"
exit 0
