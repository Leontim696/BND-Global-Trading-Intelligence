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


def test_notes_are_added_without_changing_the_verdict(tmp_path):
    path = tmp_path / "r.jsonl"
    ex.propose(path, **BASE)
    ex.finish(path, id="E-001", verdict="respins", concluzie="nu")
    ex.add_note(path, id="E-001", text="Interpretare ulterioară despre eșantion")
    state = ex.experiments(path)["E-001"]
    assert state["rezultat"]["verdict"] == "respins" and len(state["note"]) == 1
    assert "Interpretare ulterioară" in ex.report(path)
    assert ex.search(path, "interpretare")[0]["id"] == "E-001"
    with pytest.raises(ex.RegistryError):
        ex.add_note(path, id="E-009", text="x")
    with pytest.raises(ex.RegistryError):
        ex.add_note(path, id="E-001", text=" ")


def test_accepted_needs_a_p_value_or_an_explicit_justification(tmp_path):
    path = tmp_path / "r.jsonl"
    ex.propose(path, **BASE)
    with pytest.raises(ex.RegistryError, match="cere valoarea p"):
        ex.finish(path, id="E-001", verdict="acceptat", concluzie="fără test")
    with pytest.raises(ex.RegistryError, match="cere valoarea p"):           # tip=backtest: justificarea nu ajută
        ex.finish(path, id="E-001", verdict="acceptat", concluzie="x", justificare_fara_p="simulare cu limită Wilson")
    ex.propose(path, **{**BASE, "tip": "simulare", "ipoteza": "control"})
    row = ex.finish(path, id="E-002", verdict="acceptat", concluzie="control sintetic",
                    justificare_fara_p="simulare cu limită Wilson")
    assert row["justificare_fara_p"]


def test_p_value_must_be_a_probability(tmp_path):
    path = tmp_path / "r.jsonl"
    ex.propose(path, **BASE)
    for bad in (float("nan"), -0.1, 1.5, float("inf")):
        with pytest.raises(ex.RegistryError, match="între 0 și 1"):
            ex.finish(path, id="E-001", verdict="acceptat", concluzie="x", p_valoare=bad)


def test_missing_p_is_only_excused_for_simulations_and_controls(tmp_path):
    path = tmp_path / "r.jsonl"
    ex.propose(path, **BASE)                                            # tip=backtest
    with pytest.raises(ex.RegistryError, match="tipul|tipul „backtest”|backtest"):
        ex.finish(path, id="E-001", verdict="acceptat", concluzie="x", justificare_fara_p="fiindcă da")
    ex.propose(path, **{**BASE, "tip": "simulare", "ipoteza": "alta"})
    with pytest.raises(ex.RegistryError, match="justificare"):
        ex.finish(path, id="E-002", verdict="acceptat", concluzie="x")
    assert ex.finish(path, id="E-002", verdict="acceptat", concluzie="x", justificare_fara_p="control sintetic")


def test_ids_survive_a_corrupt_line_and_a_broken_registry_blocks_writes(tmp_path):
    path = tmp_path / "r.jsonl"
    ex.propose(path, **BASE)
    ex.propose(path, **{**BASE, "ipoteza": "a doua"})
    lines = path.read_text().splitlines()
    path.write_text(lines[0] + "\n" + "{rupt\n" + lines[1] + "\n")      # rând corupt la mijloc
    with pytest.raises(ex.RegistryError, match="repară"):
        ex.propose(path, **{**BASE, "ipoteza": "a treia"})              # nu se scrie peste un registru stricat
    with pytest.raises(ex.RegistryError, match="repară"):
        ex.add_note(path, id="E-001", text="x")


def test_concurrent_proposals_get_distinct_ids(tmp_path):
    import threading
    path = tmp_path / "r.jsonl"
    ids, errors = [], []

    def work(i):
        try:
            ids.append(ex.propose(path, **{**BASE, "ipoteza": f"ipoteza {i}"})["id"])
        except Exception as exc:       # pragma: no cover
            errors.append(exc)
    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert not errors and sorted(ids) == [f"E-{i:03d}" for i in range(1, 9)]
    assert ex.audit_log.verify(path)[0]
