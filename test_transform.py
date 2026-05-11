"""
FlowBridge Transform Function — Unit Tests
Run: pytest functions/tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../transform_contacts"))

from function_app import (
    clean_phone,
    clean_email,
    clean_name,
    transform_record,
    validate_record,
    safe_get,
)


# ── clean_phone ───────────────────────────────────────────────────────────
def test_clean_phone_strips_dashes():
    assert clean_phone("010-692-6593") == "0106926593"

def test_clean_phone_keeps_plus():
    assert clean_phone("+44 20 7946 0958") == "+44207946 0958".replace(" ", "")

def test_clean_phone_handles_none():
    assert clean_phone(None) == ""

def test_clean_phone_handles_empty():
    assert clean_phone("") == ""


# ── clean_email ───────────────────────────────────────────────────────────
def test_clean_email_lowercases():
    assert clean_email("Alex@EXAMPLE.COM") == "alex@example.com"

def test_clean_email_strips_whitespace():
    assert clean_email("  user@domain.com  ") == "user@domain.com"

def test_clean_email_rejects_invalid():
    assert clean_email("not-an-email") == ""

def test_clean_email_handles_none():
    assert clean_email(None) == ""


# ── clean_name ────────────────────────────────────────────────────────────
def test_clean_name_title_cases():
    assert clean_name("leanne graham") == "Leanne Graham"

def test_clean_name_collapses_whitespace():
    assert clean_name("  John   Doe  ") == "John Doe"

def test_clean_name_handles_none():
    assert clean_name(None) == ""


# ── safe_get ──────────────────────────────────────────────────────────────
def test_safe_get_nested():
    d = {"company": {"name": "Acme"}}
    assert safe_get(d, "company", "name") == "Acme"

def test_safe_get_missing_key():
    assert safe_get({}, "company", "name") == ""

def test_safe_get_non_dict_mid_path():
    d = {"company": "just a string"}
    assert safe_get(d, "company", "name") == ""


# ── transform_record ──────────────────────────────────────────────────────
SAMPLE_RAW = {
    "id": 1,
    "name": "leanne graham",
    "username": "Bret",
    "email": "Sincere@april.biz",
    "address": {"city": "Gwenborough", "zipcode": "92998-3874"},
    "phone": "1-770-736-8031 x56442",
    "website": "hildegard.org",
    "company": {"name": "Romaguera-Crona"},
}

def test_transform_normalises_name():
    result = transform_record(SAMPLE_RAW)
    assert result["full_name"] == "Leanne Graham"

def test_transform_lowercases_email():
    result = transform_record(SAMPLE_RAW)
    assert result["email"] == "sincere@april.biz"

def test_transform_strips_phone():
    result = transform_record(SAMPLE_RAW)
    assert result["phone"].isdigit() or result["phone"].startswith("+")

def test_transform_extracts_company():
    result = transform_record(SAMPLE_RAW)
    assert result["company"] == "Romaguera-Crona"

def test_transform_adds_synced_at():
    result = transform_record(SAMPLE_RAW)
    assert "synced_at" in result
    assert "T" in result["synced_at"]  # ISO format

def test_transform_sets_pipeline_ver():
    result = transform_record(SAMPLE_RAW)
    assert result["pipeline_ver"] == "1.0.0"


# ── validate_record ───────────────────────────────────────────────────────
def test_validate_passes_good_record():
    r = {"contact_id": 1, "full_name": "Jane Doe", "email": "jane@example.com"}
    valid, reason = validate_record(r)
    assert valid
    assert reason == "ok"

def test_validate_fails_missing_id():
    r = {"contact_id": None, "full_name": "Jane", "email": "jane@x.com"}
    valid, reason = validate_record(r)
    assert not valid
    assert "contact_id" in reason

def test_validate_fails_missing_name():
    r = {"contact_id": 1, "full_name": "", "email": "jane@x.com"}
    valid, reason = validate_record(r)
    assert not valid

def test_validate_fails_missing_email():
    r = {"contact_id": 1, "full_name": "Jane", "email": ""}
    valid, reason = validate_record(r)
    assert not valid
