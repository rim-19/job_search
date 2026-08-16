"""Rule-filter, prerank, and priority logic (no network)."""
from src import scorer


def test_layer1_drops_ineligible_keeps_eligible():
    jobs = [
        {"title": "Dev", "location": "Tangier, Morocco", "description": "on-site", "url": "a"},
        {"title": "Dev", "location": "Remote - Morocco", "description": "remote", "url": "b"},
    ]
    survivors, dropped = scorer.layer1_filter(jobs)
    urls = {j["url"] for j in survivors}
    assert "b" in urls and "a" not in urls
    assert dropped == 1


def test_engineer_title_not_rejected_by_rule():
    jobs = [{"title": "Junior Software Engineer", "location": "Remote - Morocco",
             "description": "remote entry level", "url": "x"}]
    survivors, _ = scorer.layer1_filter(jobs)
    assert len(survivors) == 1


def test_prerank_sinks_senior_titles():
    jobs = [
        {"title": "Senior Software Engineer", "location": "Remote", "description": "python react node"},
        {"title": "Junior Developer", "location": "Remote worldwide", "description": "python"},
    ]
    ranked = scorer._prerank(jobs)
    assert ranked[0]["title"] == "Junior Developer"


def test_prerank_lifts_casablanca():
    jobs = [
        {"title": "Developer", "location": "Casablanca, Morocco", "description": "react node"},
        {"title": "Developer", "location": "Somewhere", "description": "react node"},
    ]
    ranked = scorer._prerank(jobs)
    assert "casablanca" in ranked[0]["location"].lower()


def test_priority_from_score():
    assert scorer._priority_from_score(90) == "APPLY_NOW"
    assert scorer._priority_from_score(85) == "APPLY_NOW"
    assert scorer._priority_from_score(75) == "APPLY"
    assert scorer._priority_from_score(60) == "CONSIDER"
    assert scorer._priority_from_score(40) == "SKIP"
