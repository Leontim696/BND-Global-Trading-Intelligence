"""Audit 01.11, P2 #6: un experiment se poate repeta doar dacă sunt fixate codul, datele, costurile, criteriile și seed-urile."""
import json
from pathlib import Path


from src.bnd import experiments as ex
from src.bnd import research_lab as lab

ROOT = Path(__file__).resolve().parents[1]


def write_csv(folder, name, rows):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.csv").write_text("open_time,open,high,low,close,volume\n" + "\n".join(rows) + "\n")


def propose(path, **kw):
    base = dict(titlu="t", ipoteza="h", familie="capital", tip="backtest", criteriu="c", parametri={"cost_bps": 5},
                antrenare="2020-01-01:2020-12-31", test="2021-01-01:2021-12-31")
    return ex.propose(path, **{**base, **kw})


def test_data_manifest_changes_when_a_single_value_changes(tmp_path):
    write_csv(tmp_path, "A", ["2024-01-01T00:00:00+00:00,1,2,1,2,10", "2024-01-02T00:00:00+00:00,2,3,2,3,10"])
    first = ex.data_manifest(tmp_path)
    assert first["fisiere"]["A.csv"]["randuri"] == 2 and first["fisiere"]["A.csv"]["ultima"].startswith("2024-01-02")
    assert ex.data_manifest(tmp_path)["hash"] == first["hash"]                        # stabil
    write_csv(tmp_path, "A", ["2024-01-01T00:00:00+00:00,1,2,1,2,10", "2024-01-02T00:00:00+00:00,2,3,2,3.0001,10"])
    assert ex.data_manifest(tmp_path)["hash"] != first["hash"]                        # o zecimală schimbată


def test_finish_records_the_exact_code_with_the_result(tmp_path):
    path = tmp_path / "r.jsonl"
    propose(path, date_eticheta="x")
    row = ex.finish(path, id="E-001", verdict="respins", concluzie="nu")
    assert row["cod_la_rezultat"]["commit"] and len(row["cod_la_rezultat"]["commit"]) == 40
    assert isinstance(row["cod_la_rezultat"]["modificat"], bool)


def test_reproducibility_report_flags_each_missing_piece(tmp_path):
    path = tmp_path / "r.jsonl"
    csv_dir = tmp_path / "d"
    write_csv(csv_dir, "A", ["2024-01-01T00:00:00+00:00,1,2,1,2,10"])
    propose(path, date_fisiere=[csv_dir / "A.csv"])
    metrics = {"reproducere": {"date": ex.data_manifest(csv_dir), "seeds": {"bootstrap": 7}}}
    ex.finish(path, id="E-001", verdict="respins", concluzie="nu", metrici=metrics)
    propose(path, titlu="t2", ipoteza="h2", date_eticheta="doar etichetă")           # date nefixate
    ex.finish(path, id="E-002", verdict="respins", concluzie="nu")
    status = {r["id"]: r for r in ex.reproducibility(path)}
    assert status["E-001"]["probleme"] == [] or all("modificări necomise" in p for p in status["E-001"]["probleme"])
    assert any("nu sunt fixate prin hash" in p for p in status["E-002"]["probleme"])
    assert not status["E-002"]["reproductibil"]


def test_code_changed_between_proposal_and_result_is_flagged(tmp_path):
    path = tmp_path / "r.jsonl"
    entry = propose(path, date_eticheta="x")
    ex.finish(path, id="E-001", verdict="respins", concluzie="nu")
    lines = path.read_text().splitlines()
    # simulăm un cod diferit la propunere (înainte de rezultat) reconstruind un registru cu hash corect
    path2 = tmp_path / "r2.jsonl"
    from src.bnd import audit_log
    first = json.loads(lines[0])
    first["data"]["cod"] = "abc1234"
    audit_log.append(path2, first["kind"], first["data"])
    second = json.loads(lines[1])
    audit_log.append(path2, second["kind"], second["data"])
    assert any("codul s-a schimbat" in p for p in ex.reproducibility(path2)[0]["probleme"])
    assert entry["cod"]


def test_verify_data_detects_a_changed_or_missing_file(tmp_path):
    path = tmp_path / "r.jsonl"
    data_dir = tmp_path / "d"
    write_csv(data_dir, "A", ["2024-01-01T00:00:00+00:00,1,2,1,2,10"])
    propose(path, date_eticheta="x")
    ex.finish(path, id="E-001", verdict="respins", concluzie="nu",
              metrici={"reproducere": {"date": ex.data_manifest(data_dir)}})
    assert ex.verify_data(path, "E-001", data_dir) == []
    write_csv(data_dir, "A", ["2024-01-01T00:00:00+00:00,1,2,1,9,10"])
    assert "conținut diferit" in ex.verify_data(path, "E-001", data_dir)[0]
    (data_dir / "A.csv").unlink()
    assert "lipsește" in ex.verify_data(path, "E-001", data_dir)[0]
    propose(path, titlu="alt", ipoteza="alta", date_eticheta="y")
    ex.finish(path, id="E-002", verdict="respins", concluzie="nu")
    assert "nu are amprenta" in ex.verify_data(path, "E-002", data_dir)[0]


def test_same_inputs_give_the_same_research_result_twice():
    """Determinism: aceleași date + același cod + aceleași seed-uri = același verdict, aceleași numere."""
    a = lab.run_discovery(universes=3, markets=3, days=250)
    b = lab.run_discovery(universes=3, markets=3, days=250)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    universe_a = lab.synthetic_universe(1000, 3, 120)
    universe_b = lab.synthetic_universe(1000, 3, 120)
    assert {k: [(c.open_time, c.close) for c in v] for k, v in universe_a.items()} == \
        {k: [(c.open_time, c.close) for c in v] for k, v in universe_b.items()}
    other = lab.synthetic_universe(1001, 3, 120)
    first = next(iter(universe_a))
    assert [c.close for c in other[first]] != [c.close for c in universe_a[first]]       # alt seed = alte date


def test_bootstrap_is_deterministic_for_a_seed_and_changes_with_it():
    from datetime import datetime, timedelta, timezone

    from src.bnd.significance import bootstrap_difference
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    a = [(start + timedelta(days=i), 100 * (1 + 0.001 * i + 0.01 * ((-1) ** i))) for i in range(120)]
    b = [(start + timedelta(days=i), 100 * (1 + 0.0005 * i)) for i in range(120)]
    one = bootstrap_difference(a, b, samples=300)
    assert one == bootstrap_difference(a, b, samples=300)
    assert one["ci95_low_pct_annual"] != bootstrap_difference(a, b, samples=300, seed=99)["ci95_low_pct_annual"]


def test_research_lab_records_the_data_fingerprint_and_seeds_and_rerun_matches(tmp_path, capsys):
    from src.bnd.market_data import save_csv
    data_dir = tmp_path / "d"
    data_dir.mkdir()
    for name, candles in lab.synthetic_universe(5, 3, 900).items():
        save_csv(candles, data_dir / f"{name}.csv")
    results = []
    for run in ("a", "b"):
        path = tmp_path / f"r_{run}.jsonl"
        propose(path, date_eticheta="sintetic", parametri={"cost_bps": 15, "markets": 3, "execution": "deschidere_urmatoare",
                                                           "kelly_fraction": 0.25, "kelly_cap": 0.25, "max_leverage": 2,
                                                           "vol_target": 0.15, "financing": 0.05})
        code = lab.main(["capital", "--id", "E-001", "--data-dir", str(data_dir), "--registru", str(path),
                         "--accept-deviation", "date sintetice de test"])
        assert code == 0
        results.append(ex.experiments(path)["E-001"]["rezultat"])
    repro = results[0]["metrici"]["reproducere"]
    assert repro["date"]["hash"] and repro["seeds"] == {"bootstrap": 7}
    assert repro["date"] == results[1]["metrici"]["reproducere"]["date"]                    # aceleași date
    assert results[0]["verdict"] == results[1]["verdict"] and results[0]["p_valoare"] == results[1]["p_valoare"]
    assert results[0]["metrici"]["summary"] == results[1]["metrici"]["summary"]          # aceleași numere
    assert ex.verify_data(tmp_path / "r_a.jsonl", "E-001", data_dir) == []
    # un singur CSV schimbat => verificarea datelor îl găsește
    changed = lab.synthetic_universe(6, 3, 900)["S0"]
    save_csv(changed, data_dir / "S0.csv")
    assert "S0.csv: conținut diferit" in ex.verify_data(tmp_path / "r_a.jsonl", "E-001", data_dir)[0]


def test_real_registry_gaps_are_reported_honestly():
    """Experimentele vechi (E-001..E-012) au date doar cu etichetă: raportul nu le declară reproductibile complet."""
    status = {r["id"]: r for r in ex.reproducibility(ROOT / "experimente/registru.jsonl")}
    assert status and not any(r["reproductibil"] for r in status.values())
    assert any("nu sunt fixate prin hash" in p for r in status.values() for p in r["probleme"])
