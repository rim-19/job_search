"""Cross-source deduplication (item 21)."""
from src import dedupe


def test_canonical_url_strips_tracking_and_slash():
    a = dedupe.canonical_url("https://Example.com/jobs/123/?utm_source=x&gh_src=y")
    b = dedupe.canonical_url("https://example.com/jobs/123")
    assert a == b


def test_same_job_different_links_collapses():
    jobs = [
        {"title": "Backend Dev", "company": "Acme", "url": "https://x.com/j/1?utm_source=rss"},
        {"title": "Backend Dev", "company": "Acme", "url": "https://x.com/j/1/"},
    ]
    out = dedupe.dedupe(jobs)
    assert len(out) == 1


def test_cross_source_title_company_collapses():
    jobs = [
        {"title": "Junior Developer", "company": "Acme", "url": "https://remotive.com/a"},
        {"title": "Junior  Developer!", "company": "acme", "url": "https://weworkremotely.com/b"},
    ]
    out = dedupe.dedupe(jobs)
    assert len(out) == 1  # same title+company, different source -> one record


def test_empty_company_not_over_merged():
    jobs = [
        {"title": "Developer", "company": "", "url": "https://a.com/1"},
        {"title": "Developer", "company": "", "url": "https://b.com/2"},
    ]
    out = dedupe.dedupe(jobs)
    assert len(out) == 2  # no company -> don't collapse distinct URLs


def test_missing_url_dropped():
    assert dedupe.dedupe([{"title": "X", "company": "Y", "url": ""}]) == []
