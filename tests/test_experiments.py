import pytest

from src.bnd import experiments as ex

BASE = dict(titlu="Vol țintă", ipoteza="Volatilitatea țintă bate dimensiunea fixă", familie="capital",
            tip="backtest", criteriu="Sharpe mai mare după costuri, p<0.05 corectat")


def test_propose_and_finish(tmp_path):
    path = tmp_path / "r.jsonl"
    e = ex.propose(path, **BASE, antrenare="2015-01-01:2019-12-31", test="2020-01-01:2024-12-31")
    assert e["id"] == "E-001" and e["numar_in_familie"] == 1
    row = ex.finish(path, id="E-001", verdict="respins", concluzie="Nu bate varianta simplă", cost_usd=0.0)
    assert row["verdict"] == "respins"
    assert ex.experiments(path)["E-001"]["stare"] == "încheiat"
    assert "E-001" in ex.report(path) and "corect" in ex.report(path)


def test_test_period_must_follow_training(tmp_path):
    with pytest.raises(ex.RegistryError, match="după sfârșitul"):
        ex.propose(tmp_path / "r.jsonl", **BASE, antrenare="2015-01-01:2020-06-30", test="2020-01-01:2024-12-31")


def test_test_cannot_exceed_information_date(tmp_path):
    with pytest.raises(ex.RegistryError, match="info_pana_la"):
        ex.propose(tmp_path / "r.jsonl", **BASE, test="2020-01-01:2026-12-31", info_pana_la="2026-10-31")


def test_duplicate_needs_justification(tmp_path):
    path = tmp_path / "r.jsonl"
    ex.propose(path, **BASE)
    with pytest.raises(ex.RegistryError, match="duplicat"):
        ex.propose(path, **BASE)
    again = ex.propose(path, **BASE, justificare_duplicat="date noi")
    assert again["duplicat_al"] == "E-001"


def test_criterion_required_and_results_not_rewritten(tmp_path):
    path = tmp_path / "r.jsonl"
    with pytest.raises(ex.RegistryError, match="criteriu"):
        ex.propose(path, **{**BASE, "criteriu": " "})
    ex.propose(path, **BASE)
    ex.finish(path, id="E-001", verdict="neconcludent", concluzie="prea puține date")
    with pytest.raises(ex.RegistryError, match="deja încheiat"):
        ex.finish(path, id="E-001", verdict="acceptat", concluzie="schimbat")
    with pytest.raises(ex.RegistryError, match="nu există"):
        ex.finish(path, id="E-009", verdict="respins", concluzie="x")
    with pytest.raises(ex.RegistryError, match="concluzia"):
        ex.finish(path, id="E-001", verdict="respins", concluzie="")


def test_multiple_testing_correction(tmp_path):
    path = tmp_path / "r.jsonl"
    for i in range(5):
        ex.propose(path, **{**BASE, "ipoteza": f"ipoteza {i}"})
    with pytest.raises(ex.RegistryError, match="0.0100"):
        ex.finish(path, id="E-001", verdict="acceptat", concluzie="p=0.03", p_valoare=0.03)
    assert ex.finish(path, id="E-001", verdict="acceptat", concluzie="p=0.004", p_valoare=0.004)


def test_search_and_tamper_detection(tmp_path):
    path = tmp_path / "r.jsonl"
    ex.propose(path, **BASE)
    assert ex.search(path, "volatilitatea țintă")[0]["id"] == "E-001"
    path.write_text(path.read_text().replace("Vol țintă", "Altceva"), encoding="utf-8")
    assert "STRICAT" in ex.report(path)


def test_data_files_are_hashed(tmp_path):
    data = tmp_path / "d.csv"
    data.write_text("a,b\n1,2\n")
    e = ex.propose(tmp_path / "r.jsonl", **BASE, date_fisiere=[data])
    assert list(e["date"].values())[0] == ex.file_hash(data)


def test_cli(tmp_path, capsys):
    path = str(tmp_path / "r.jsonl")
    assert ex.main(["--registru", path, "propune", "--titlu", "t", "--ipoteza", "i", "--familie", "f",
                    "--tip", "backtest", "--criteriu", "c"]) == 0
    assert ex.main(["--registru", path, "rezultat", "E-001", "--verdict", "respins", "--concluzie", "nu"]) == 0
    assert ex.main(["--registru", path, "verifica"]) == 0
    assert ex.main(["--registru", path, "rezultat", "E-001", "--verdict", "respins", "--concluzie", "nu"]) == 2
    capsys.readouterr()
