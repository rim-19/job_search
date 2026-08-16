"""Geographic eligibility rules (item 51 of the spec)."""
from src import geo


def elig(title, location, desc=""):
    return geo.classify({"title": title, "location": location, "description": desc})["eligible_for_rim"]


def test_casablanca_onsite_accept():
    assert elig("Full-Stack Developer", "Casablanca, Morocco", "on-site role") == "true"

def test_rabat_onsite_accept():
    assert elig("Backend Developer", "Rabat, Morocco", "onsite") == "true"

def test_tangier_onsite_reject():
    assert elig("Software Developer", "Tangier, Morocco", "on-site") == "false"

def test_marrakech_hybrid_reject():
    assert elig("Web Developer", "Marrakech", "hybrid, 3 days in office") == "false"

def test_morocco_remote_accept():
    assert elig("Developer", "Remote - Morocco", "fully remote") == "true"

def test_worldwide_remote_accept():
    assert elig("AI Developer", "Anywhere in the World", "remote") == "true"

def test_us_work_authorization_reject():
    assert elig("React Developer", "Remote", "must be authorized to work in the US") == "false"

def test_us_only_reject():
    assert elig("Developer", "US Only", "remote") == "false"

def test_canada_only_reject():
    assert elig("Developer", "Canada Only", "remote") == "false"

def test_uk_work_authorization_reject():
    assert elig("Developer", "Remote (UK)", "right to work in the UK required") == "false"

def test_emea_uncertain():
    assert elig("Engineer", "EMEA", "remote, CET hours") == "uncertain"

def test_africa_remote_accept():
    assert elig("Developer", "Remote - Africa", "remote") == "true"

def test_onsite_abroad_reject():
    assert elig("Developer", "Berlin, Germany", "on-site") == "false"

def test_engineer_title_does_not_affect_geo():
    # geo judges geography only; a Casablanca on-site role is geo-eligible
    # regardless of the (mis)leading title. Seniority is handled elsewhere.
    assert elig("Senior Software Engineer", "Casablanca, Morocco", "on-site") == "true"
