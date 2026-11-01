"""Validează argumentele libere primite de la un utilizator înainte să ajungă în CLI-uri care țin contul.

Un câmp de workflow cu text liber ("--strategy x --portfolio-vol 15 ...") era despicat în cuvinte și dat direct
codului. Aici fiecare cuvânt trebuie să fie un steag dintr-o listă albă, cu valoarea de tipul cerut: numere,
numere întregi, alegeri fixe sau nume simple. Căi (`--state`, `--out`, `--report`, `--audit-log`, `--data-dir`,
`--signals`...), steaguri necunoscute și orice caracter neobișnuit sunt refuzate.

    python scripts/safe_args.py "--strategy regime_switch --max-leverage 3"   # tipărește argumentele validate
Cod de ieșire 2 și un mesaj la stderr dacă ceva e refuzat.
"""

import re
import shlex
import sys

NUMBER = re.compile(r"-?\d{1,9}(\.\d{1,9})?")
INTEGER = re.compile(r"\d{1,9}")
WORD = re.compile(r"[a-z][a-z0-9_]{0,40}")
NAMES = re.compile(r"[A-Za-z0-9_]{1,24}(,[A-Za-z0-9_]{1,24}){0,120}")
RANGE = re.compile(r"\d{1,6}:\d{1,6}(:\d{1,6})?")
NAMED_RANGE = re.compile(r"[a-z_]{1,30}=\d{1,6}:\d{1,6}:\d{1,6}")
PARAM = re.compile(r"[a-z_]{1,30}=-?\d{1,9}(\.\d{1,9})?")

FLAGS = {}
for name in ("funding cash-rate rebalance equity fee slippage allocation leverage max-leverage stop-loss "
             "risk-per-trade max-daily-loss max-drawdown in-sample portfolio-vol max-weight max-group-weight "
             "financing stop-atr max-sector disable-below").split():
    FLAGS["--" + name] = NUMBER
for name in "sizing-lookback permutations seed train test embargo disable-after train-days test-days window".split():
    FLAGS["--" + name] = INTEGER
for name in ("allow-short no-risk-gate require-continuous full-grid no-switch-off no-shorts skip-missing").split():
    FLAGS["--" + name] = None                                  # steag fără valoare
FLAGS.update({
    "--base-currency": {"USD", "EUR", "GBP", "AUD"}, "--sizing": {"volatility", "equal"},
    "--mode": {"rolling", "expanding"},
    "--universe": {"futures", "etf", "stocks", "crypto", "ai", "unic", "defense"},
    "--strategy": WORD, "--members": re.compile(r"[a-z][a-z0-9_]{0,40}(,[a-z][a-z0-9_]{0,40}){0,20}"),
    "--markets": NAMES, "--classes": NAMES, "--param": PARAM, "--range": NAMED_RANGE,
    "--fast-range": RANGE, "--slow-range": RANGE, "--entry-range": RANGE, "--exit-range": RANGE,
    "--target-vol-range": RANGE, "--vol-lookback-range": RANGE,
})


class UnsafeArguments(ValueError):
    pass


def _accepts(rule, value: str) -> bool:
    return value in rule if isinstance(rule, set) else bool(rule.fullmatch(value))


def validate(text: str) -> list[str]:
    try:
        tokens = shlex.split(text or "")
    except ValueError as exc:
        raise UnsafeArguments(f"ghilimele neînchise: {exc}") from exc
    if len(tokens) > 60:
        raise UnsafeArguments("prea multe argumente (maxim 60)")
    out, i = [], 0
    while i < len(tokens):
        token = tokens[i]
        if "=" in token and token.startswith("--"):
            flag, value = token.split("=", 1)
            tokens[i:i + 1] = [flag, value]
            token = flag
        if token not in FLAGS:
            raise UnsafeArguments(f"steag nepermis: {token[:40]!r}")
        rule = FLAGS[token]
        out.append(token)
        i += 1
        if rule is None:
            continue
        if i >= len(tokens) or not _accepts(rule, tokens[i]):
            shown = tokens[i][:40] if i < len(tokens) else "(lipsește)"
            raise UnsafeArguments(f"valoare nepermisă pentru {token}: {shown!r}")
        out.append(tokens[i])
        i += 1
    return out


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Folosire: safe_args.py \"<argumente>\"", file=sys.stderr)
        return 2
    try:
        print(" ".join(validate(args[0])))
    except UnsafeArguments as exc:
        print(f"::error::Argumente refuzate: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
