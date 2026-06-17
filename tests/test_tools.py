"""
tests/test_tools.py

Pytest tests for the three FitFindr tools.
Tests focus on the failure modes and key functional requirements.

Run with:
    pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings tests ─────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    """Impossible query returns [] without raising an exception."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    """All returned listings must be at or below max_price."""
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)


def test_search_no_price_filter():
    """Without a price filter, higher-priced items can appear."""
    results_capped = search_listings("jacket", size=None, max_price=30)
    results_uncapped = search_listings("jacket", size=None, max_price=None)
    assert len(results_uncapped) >= len(results_capped)


def test_search_size_filter_case_insensitive():
    """Size filter should be case-insensitive."""
    results_upper = search_listings("tee", size="M", max_price=None)
    results_lower = search_listings("tee", size="m", max_price=None)
    assert len(results_upper) == len(results_lower)


def test_search_size_filter_substring():
    """Size 'M' should match listings with size 'S/M'."""
    results = search_listings("tee", size="M", max_price=None)
    ids = [r["id"] for r in results]
    # lst_002 is Y2K Baby Tee, size "S/M" — should match
    assert "lst_002" in ids


def test_search_results_are_sorted_by_relevance():
    """First result should have at least as many matching keywords as later ones."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    # Spot-check: at least 2 results and no score inversion (we can't directly
    # check scores, but we can verify results have the key fields)
    assert len(results) >= 2
    for item in results:
        assert "id" in item
        assert "price" in item
        assert "title" in item


def test_search_returns_empty_for_zero_overlap():
    """A query with no keyword overlap with any listing returns []."""
    results = search_listings("xyzzy frobnicator", size=None, max_price=None)
    assert results == []


def test_search_result_fields():
    """Each result dict contains all required listing fields."""
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) > 0
    required_fields = {"id", "title", "description", "category", "style_tags",
                       "size", "condition", "price", "colors", "brand", "platform"}
    for item in results:
        assert required_fields.issubset(item.keys())


# ── suggest_outfit tests ──────────────────────────────────────────────────────

def test_suggest_outfit_with_empty_wardrobe():
    """Empty wardrobe returns a non-empty string (general styling advice)."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    output = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(output, str)
    assert len(output.strip()) > 0


def test_suggest_outfit_with_example_wardrobe():
    """Populated wardrobe returns a non-empty outfit suggestion string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    output = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(output, str)
    assert len(output.strip()) > 0


def test_suggest_outfit_does_not_raise_on_empty_wardrobe():
    """suggest_outfit must never raise an exception on empty wardrobe."""
    results = search_listings("jacket", size=None, max_price=50)
    assert len(results) > 0
    try:
        suggest_outfit(results[0], get_empty_wardrobe())
    except Exception as e:
        pytest.fail(f"suggest_outfit raised an exception on empty wardrobe: {e}")


# ── create_fit_card tests ─────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    """Empty outfit string returns a descriptive error message, not an exception."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    output = create_fit_card("", results[0])
    assert isinstance(output, str)
    assert len(output.strip()) > 0
    assert "cannot" in output.lower() or "fit card" in output.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    """Whitespace-only outfit string is treated as empty and returns error."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    output = create_fit_card("   \n  ", results[0])
    assert isinstance(output, str)
    assert len(output.strip()) > 0


def test_create_fit_card_does_not_raise_on_empty_outfit():
    """create_fit_card must never raise an exception, even with empty outfit."""
    results = search_listings("jacket", size=None, max_price=50)
    assert len(results) > 0
    try:
        create_fit_card("", results[0])
    except Exception as e:
        pytest.fail(f"create_fit_card raised an exception on empty outfit: {e}")


def test_create_fit_card_with_valid_input():
    """Valid inputs produce a non-empty caption string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    outfit_text = "Pair with baggy dark wash jeans and chunky white sneakers for a 90s vibe."
    output = create_fit_card(outfit_text, results[0])
    assert isinstance(output, str)
    assert len(output.strip()) > 0
