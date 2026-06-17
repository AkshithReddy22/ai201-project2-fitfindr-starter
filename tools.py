"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive substring (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    # Step 1: Apply hard filters
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    if size is not None:
        size_lower = size.lower().strip()
        listings = [
            item for item in listings
            if size_lower in item["size"].lower()
        ]

    # Step 2: Score by keyword overlap with description
    keywords = set(re.sub(r"[^a-z0-9 ]", "", description.lower()).split())

    def score(item: dict) -> int:
        # Build a bag of words from all searchable fields
        searchable = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            " ".join(item.get("style_tags", [])),
            " ".join(item.get("colors", [])),
            item.get("brand", "") or "",
        ]).lower()
        tokens = set(re.sub(r"[^a-z0-9 ]", "", searchable).split())
        return len(keywords & tokens)

    scored = [(item, score(item)) for item in listings]

    # Step 3: Drop items with score 0 (no overlap at all)
    scored = [(item, s) for item, s in scored if s > 0]

    # Step 4: Sort highest score first
    scored.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handled gracefully.

    Returns:
        A non-empty string with outfit suggestions. If the wardrobe is empty,
        returns general styling advice instead of crashing.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Unable to generate outfit suggestion: {e}"

    item_summary = (
        f"Title: {new_item.get('title', 'Unknown item')}\n"
        f"Category: {new_item.get('category', '')}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Description: {new_item.get('description', '')}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe — give general styling advice
        prompt = (
            f"A user is considering buying this secondhand item:\n\n"
            f"{item_summary}\n\n"
            "They haven't told you what's in their wardrobe yet. "
            "Give them 2–3 sentences of general styling advice: what kinds of pieces pair well "
            "with this item, what aesthetic it suits, and one styling tip. "
            "Be specific and conversational — talk to them like a knowledgeable friend, not a product page."
        )
    else:
        # Build wardrobe list for the prompt
        wardrobe_lines = []
        for w in wardrobe_items:
            notes = f" ({w['notes']})" if w.get("notes") else ""
            wardrobe_lines.append(
                f"- {w['name']} [{w['category']}]{notes}"
            )
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"A user is considering buying this secondhand item:\n\n"
            f"{item_summary}\n\n"
            f"Their current wardrobe includes:\n{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfit combinations using the new item and specific named pieces "
            "from their wardrobe. For each outfit, name the exact wardrobe pieces you're pairing it with "
            "and describe the vibe in 1–2 sentences. Be conversational and specific — this should feel "
            "like advice from someone who actually knows fashion."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=400,
        )
        result = response.choices[0].message.content.strip()
        return result if result else f"This {new_item.get('category', 'item')} pairs well with basics — try building an outfit around its color palette."
    except Exception as e:
        category = new_item.get("category", "item")
        return (
            f"Unable to generate outfit suggestion right now. "
            f"The item is a {category} — try pairing it with complementary basics."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string.
    """
    # Guard against empty outfit
    if not outfit or not outfit.strip():
        return (
            "Cannot generate a fit card without an outfit suggestion. "
            "Please provide outfit details."
        )

    title = new_item.get("title", "this piece")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift platform")
    condition = new_item.get("condition", "")

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok OOTD caption for this thrifted outfit:\n\n"
        f"Thrifted item: {title} — ${price} from {platform} ({condition} condition)\n"
        f"Outfit: {outfit}\n\n"
        "Rules:\n"
        "- Sound like a real person posting their outfit online, not a product description\n"
        "- Mention the item name, price, and platform naturally, exactly once each\n"
        "- Be specific about the vibe of the outfit\n"
        "- Keep it casual, fun, and under 80 words\n"
        "- Do NOT use marketing language like 'perfect', 'stunning', or 'must-have'\n"
        "Output only the caption text — no labels, no quotes around it."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,
            max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        return result if result else f"thrifted {title} for ${price} off {platform} and building outfits around it 🖤"
    except Exception as e:
        return (
            f"Fit card generation failed — but here's the item: "
            f"{title} for ${price} on {platform}."
        )
