"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.
    """
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Use the Groq LLM to extract description, size, and max_price from the
    user's natural-language query. Falls back to safe defaults if parsing fails.

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"description": query, "size": None, "max_price": None}

    system_prompt = (
        "You are a query parser for a secondhand clothing search app. "
        "Extract the following from the user's query and return ONLY valid JSON — no markdown, no explanation:\n"
        '{"description": "<item keywords>", "size": "<size or null>", "max_price": <number or null>}\n\n'
        "Rules:\n"
        "- description: the item type and style keywords (e.g. 'vintage graphic tee', '90s track jacket')\n"
        "- size: the size string if mentioned (e.g. 'M', 'S/M', 'US 8'), otherwise null\n"
        "- max_price: the maximum price as a float if mentioned (e.g. 30.0), otherwise null\n"
        "Return ONLY the JSON object, nothing else."
    )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            max_tokens=100,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        parsed = json.loads(raw)
        return {
            "description": parsed.get("description") or query,
            "size": parsed.get("size") or None,
            "max_price": float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
        }
    except Exception:
        # Fall back: use the full query as the description
        return {"description": query, "size": None, "max_price": None}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        The session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion / fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into structured parameters
    session["parsed"] = _parse_query(query)
    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    # Step 3: Search for listings
    session["search_results"] = search_listings(description, size, max_price)

    # Branch: no results → early exit
    if not session["search_results"]:
        desc_display = description
        size_note = f", size {size}" if size else ""
        price_note = f" under ${max_price:.0f}" if max_price else ""
        session["error"] = (
            f"No listings found for '{desc_display}'{size_note}{price_note}. "
            "Try a broader description, remove the size filter, or raise your price limit."
        )
        return session

    # Step 4: Select the top result
    session["selected_item"] = session["search_results"][0]

    # Step 5: Suggest an outfit
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
    )

    # Step 6: Generate the fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    # Step 7: Return completed session (error remains None)
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
