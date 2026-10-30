"""The offline demo must run end to end without network access."""

from src.bnd.paper_demo import run_demo


def test_demo_runs_end_to_end():
    result = run_demo()

    # Mock agents all vote HOLD, so no paper trade is opened.
    assert result["trade"]["status"] == "NO_TRADE"
    assert result["trade"]["reason"] == "Council voted HOLD"
    assert result["debate"]["status"] == "CLOSED"
    assert result["debate"]["council"]["current_decision"] == "HOLD"
