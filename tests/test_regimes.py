"""Regimuri de piață: etichete fără informație din viitor și defalcarea rezultatelor."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.market_data import Candle
from src.bnd.regimes import REGIMES, label_regimes, regime_breakdown

T0 = datetime(2020, 1, 1, tzinfo=timezone.utc)


def series(moves):
    price, out = 100.0, []
    for i, move in enumerate(moves):
        close = price * (1 + move)
        out.append(Candle(T0 + timedelta(days=i), price, max(price, close), min(price, close), close, 1))
        price = close
    return out


def calm_up(n):
    return [0.002 + 0.0005 * (-1) ** i for i in range(n)]


def wild(n, drift=0.0):
    return [drift + 0.03 * (-1) ** i for i in range(n)]


def test_labels_follow_trend_and_volatility():
    candles = series(calm_up(300) + wild(60, 0.004) + calm_up(5))

    labels = label_regimes(candles)

    assert labels[candles[250].open_time] == "urcare calmă"
    assert labels[candles[340].open_time] == "urcare agitată"
    assert set(labels.values()) <= set(REGIMES)
    assert min(labels) >= candles[200].open_time          # nu etichetează fără istoric


def test_downtrend_is_detected():
    candles = series(calm_up(250) + [-0.01 + 0.0005 * (-1) ** i for i in range(120)])

    labels = label_regimes(candles)

    assert labels[candles[-1].open_time].startswith("scădere")


def test_a_label_never_uses_later_data():
    base = series(calm_up(300) + wild(40))
    changed = series(calm_up(300) + wild(40)[:-1] + [0.5])        # doar ultima zi diferă

    first, second = label_regimes(base), label_regimes(changed)

    last = base[-1].open_time
    assert {d: v for d, v in first.items() if d != last} == {d: v for d, v in second.items() if d != last}


def test_breakdown_assigns_each_return_to_the_previous_days_regime():
    labels = {T0: "urcare calmă", T0 + timedelta(days=2): "scădere agitată"}
    curve = [(T0 + timedelta(days=i), v) for i, v in enumerate([100, 110, 121, 90.75, 81.675])]

    table = regime_breakdown(curve, labels)

    # zilele 0->1, 1->2 sub «urcare calmă» (+10% și +10%); 2->3, 3->4 sub «scădere agitată» (-25%, -10%).
    assert table["urcare calmă"]["days"] == 2 and table["urcare calmă"]["return_pct"] == pytest.approx(21)
    assert table["scădere agitată"]["days"] == 2
    assert table["scădere agitată"]["return_pct"] == pytest.approx(100 * (0.75 * 0.9 - 1))
    assert table["urcare agitată"]["days"] == 0 and table["urcare agitată"]["sharpe"] is None


def test_validation():
    with pytest.raises(ValueError):
        label_regimes(series(calm_up(50)), trend_days=5)
