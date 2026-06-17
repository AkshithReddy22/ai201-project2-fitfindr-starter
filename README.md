# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. FitFindr orchestrates three tools — searching listings, suggesting outfits, and generating a shareable fit card — through a planning loop that responds to what each tool returns.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

Run the CLI test:
```bash
python agent.py
```

Run the tests:
```bash
pytest tests/
```

---

## Tool Inventory

### Tool 1: `search_listings`

**Function signature:** `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`

| Parameter | Type | Purpose |
|-----------|------|---------|
| `description` | `str` | Keywords describing the item (e.g. "vintage graphic tee"). Used to score each listing by keyword overlap. |
| `size` | `str \| None` | Size filter — case-insensitive substring match against the listing's size field (e.g. "M" matches "S/M"). Pass `None` to skip size filtering. |
| `max_price` | `float \| None` | Maximum price inclusive. Listings priced above this are excluded before scoring. Pass `None` to skip price filtering. |

**Returns:** A `list[dict]` of matching listing dicts sorted by relevance score (highest first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str). Returns `[]` if nothing matches — never raises an exception.

**Purpose:** Searches the 40-item mock listings dataset by filtering on price and size (if provided), then scoring each remaining listing by counting how many description keywords appear in its title, description, style_tags, colors, category, and brand fields. Returns results sorted by score so the agent always picks the best match as `results[0]`.

---

### Tool 2: `suggest_outfit`

**Function signature:** `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

| Parameter | Type | Purpose |
|-----------|------|---------|
| `new_item` | `dict` | A listing dict — the item the user is considering. Used fields: `title`, `description`, `category`, `style_tags`, `colors`, `condition`. |
| `wardrobe` | `dict` | A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has: `id`, `name`, `category`, `colors`, `style_tags`, `notes`. May be an empty list. |

**Returns:** A non-empty `str` with 1–2 outfit suggestions. When the wardrobe is populated, the response names specific wardrobe pieces (e.g. "your baggy straight-leg jeans and chunky white sneakers"). When the wardrobe is empty, the response is general styling advice about what pairs well with the item and what aesthetic it suits.

**Purpose:** Calls the Groq LLM (llama-3.3-70b-versatile) with a prompt that includes the thrifted item's details and the user's wardrobe items. The LLM suggests specific outfit combinations using named wardrobe pieces. Handles the empty wardrobe case with a different prompt — never crashes.

---

### Tool 3: `create_fit_card`

**Function signature:** `create_fit_card(outfit: str, new_item: dict) -> str`

| Parameter | Type | Purpose |
|-----------|------|---------|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit`. Must be non-empty. |
| `new_item` | `dict` | The listing dict for the thrifted item. Used fields: `title`, `price`, `platform`, `condition`. |

**Returns:** A 2–4 sentence `str` formatted as a social-media OOTD caption. Mentions the item name, price, and platform naturally once each. Sounds casual and specific. If `outfit` is empty or whitespace, returns the error string "Cannot generate a fit card without an outfit suggestion. Please provide outfit details." — never raises an exception.

**Purpose:** Calls the Groq LLM at `temperature=1.1` (higher than default) so the output varies meaningfully across different inputs and runs. The prompt explicitly instructs the LLM to write like a real person posting an OOTD, not a product description.

---

## How the Planning Loop Works

The planning loop in `run_agent()` (`agent.py`) uses a conditional sequence controlled by the session state dict. It does not call all tools unconditionally — its behavior depends on what each step returns.

**Step-by-step conditional logic:**

1. **Initialize session** — `_new_session(query, wardrobe)` creates a dict with all output fields set to `None`.

2. **Parse the query** — the Groq LLM is called with the raw user query and a system prompt asking it to return JSON: `{"description": str, "size": str|null, "max_price": float|null}`. If JSON parsing fails, the full query is used as `description` with `size=None` and `max_price=None`. Result stored in `session["parsed"]`.

3. **Call `search_listings`** — runs with the parsed parameters. Result stored in `session["search_results"]`.
   - **If `search_results` is empty** → set `session["error"]` to a specific message and **return immediately**. `suggest_outfit` and `create_fit_card` are never called.
   - **If `search_results` is non-empty** → set `session["selected_item"] = search_results[0]` and continue.

4. **Call `suggest_outfit`** — receives `session["selected_item"]` and `session["wardrobe"]`. The tool handles the empty-wardrobe case internally. Result stored in `session["outfit_suggestion"]`.

5. **Call `create_fit_card`** — receives `session["outfit_suggestion"]` and `session["selected_item"]`. The tool guards against empty outfit strings internally. Result stored in `session["fit_card"]`.

6. **Return session** — `session["error"]` is `None` on the happy path.

The key adaptive behavior: the agent behaves differently for queries that produce no results vs. queries that match listings. Steps 4 and 5 only execute if step 3 found results.

---

## State Management

All state for a single interaction lives in a session dict initialized by `_new_session()`. No data is passed by re-prompting the user.

| Key | Type | Set in step | Used in step |
|-----|------|-------------|--------------|
| `query` | `str` | 1 (init) | 2 (parsing) |
| `parsed` | `dict` | 2 (LLM parse) | 3 (search) |
| `search_results` | `list[dict]` | 3 (search) | branch check + step 4 setup |
| `selected_item` | `dict \| None` | 3 (after branch B) | 4 (suggest), 5 (fit card) |
| `wardrobe` | `dict` | 1 (init) | 4 (suggest) |
| `outfit_suggestion` | `str \| None` | 4 (suggest) | 5 (fit card) |
| `fit_card` | `str \| None` | 5 (fit card) | returned to caller |
| `error` | `str \| None` | 3 (if empty results) | returned to caller |

The `selected_item` dict that flows from step 3 into `suggest_outfit` is the exact same dict object — not a copy, not a re-lookup. Similarly, the `outfit_suggestion` string from step 4 is passed directly into `create_fit_card` in step 5. The session dict is returned to `handle_query()` in `app.py`, which reads each field to populate the three UI panels.

---

## Error Handling

### Per-tool failure modes

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the description/size/price combination — returns `[]` | `run_agent` sets `session["error"]` to "No listings found for '[description]'[size/price context]. Try a broader description, remove the size filter, or raise your price limit." and returns immediately. `suggest_outfit` and `create_fit_card` are never called. The error appears in the first UI panel; the other two are empty. |
| `suggest_outfit` | `wardrobe["items"]` is empty (new user with no wardrobe) | The tool detects the empty list before calling the LLM and switches to a different prompt requesting general styling advice. Returns a non-empty string like "Since your wardrobe is empty, here's how to style this piece: …" — never raises an exception or returns an empty string. |
| `create_fit_card` | `outfit` argument is empty or whitespace-only | Returns the error string "Cannot generate a fit card without an outfit suggestion. Please provide outfit details." without calling the LLM. This prevents a malformed or empty caption from reaching the user. |

### Concrete tested example

**Triggering the `search_listings` failure:** Running the following produces `[]` without raising an exception:

```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```

When the same impossible query is run through the full agent:
```bash
python -c "
from agent import run_agent
from utils.data_loader import get_example_wardrobe
s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe())
print(s['error'])
print('fit_card:', s['fit_card'])
"
# Output:
# No listings found for 'designer ballgown', size XXS under $5. Try a broader description, remove the size filter, or raise your price limit.
# fit_card: None
```

**Triggering the `create_fit_card` failure:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# Output: Cannot generate a fit card without an outfit suggestion. Please provide outfit details.
```

**Triggering the `suggest_outfit` empty-wardrobe case:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
# Output: [general styling advice for the item — no exception raised]
```

---

## Interaction Walkthrough

**User query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Tool called: (LLM parse, internal)**
- Tool: `_parse_query()` — Groq LLM called with system prompt
- Input: raw user query
- Why: extract structured parameters (description, size, max_price) from natural language
- Output: `{"description": "vintage graphic tee", "size": null, "max_price": 30.0}`

**Step 2 — Tool called: `search_listings`**
- Tool: `search_listings`
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why: find secondhand listings that match the user's request within budget
- Output: List starting with lst_006 "Graphic Tee — 2003 Tour Bootleg Style" ($24, depop), lst_033 "Vintage Band Tee — Faded Grey" ($19, depop), etc. Agent sets `selected_item = results[0]`.

**Step 3 — Tool called: `suggest_outfit`**
- Tool: `suggest_outfit`
- Input: `new_item=<Graphic Tee listing dict>`, `wardrobe=<example wardrobe with 10 items>`
- Why: generate outfit ideas using the found item and the user's existing wardrobe pieces
- Output: "Outfit 1: Pair this boxy graphic tee with your baggy straight-leg dark wash jeans and chunky white sneakers — tuck the front corner slightly for a 90s streetwear look. Add the black crossbody bag to finish it off. Outfit 2: Layer your vintage black denim jacket over the tee, switch to your wide-leg khaki trousers and combat boots for a grungier take."

**Step 4 — Tool called: `create_fit_card`**
- Tool: `create_fit_card`
- Input: `outfit=<outfit suggestion from Step 3>`, `new_item=<Graphic Tee listing dict>`
- Why: produce a shareable OOTD caption the user can copy for social media
- Output: "found this faded bootleg tee on depop for $24 and honestly it was made for baggy jeans 🖤 front tuck + chunky sneakers = the only look i know. full fit in my stories"

**Final output to user:**
- Panel 1 (Top listing found): Formatted card showing title, price ($24.00), platform (depop), size (L), condition (good), colors (black), style tags (graphic tee, vintage, grunge, streetwear, band tee), and description.
- Panel 2 (Outfit idea): The multi-outfit suggestion from Step 3.
- Panel 3 (Your fit card): The OOTD caption from Step 4.

---

## Spec Reflection

**One way planning.md helped during implementation:**

Writing out the exact branch logic in the Planning Loop section ("if `len(session['search_results']) == 0`, set error and return early — do NOT proceed to `suggest_outfit`") made it impossible to accidentally call `suggest_outfit` with empty input. Without this pre-written guard, I might have let the agent proceed and only discovered the bug when the LLM received a confusing prompt about a null item. The spec forced me to handle the failure mode before thinking about the happy path.

**One divergence from the spec, and why:**

The spec described using "regex or string splitting" to parse the query for size and price. During implementation, I found that users express size and price in too many varied ways ("size M", "in a medium", "under $30", "no more than 30 dollars") for a simple regex to cover reliably. I switched to using the Groq LLM as the parser (the spec also listed this as an option: "ask the LLM to parse it") because it handles natural-language variation far better. The fallback (use the full query as description) ensures the tool never crashes if the LLM parse fails. I documented this choice in the AI Tool Plan section of planning.md.

---

## AI Usage

### Instance 1 — Implementing `search_listings`

**What I directed the AI to do:** I gave Claude the Tool 1 spec block from planning.md (description of inputs with types, exact return value fields, and the failure mode stating it returns `[]` and never raises) and asked it to implement `search_listings` using `load_listings()` from `utils/data_loader.py`. I specified the scoring approach: count keyword overlaps across title, description, style_tags, colors, category, and brand, then sort by score descending.

**What I reviewed and revised:** The generated code used Python's `str.split()` for tokenization, which would not strip punctuation from the listing text — searching for "tee" might miss "tee," in the description. I revised it to use `re.sub(r"[^a-z0-9 ]", "", text).split()` for both the query keywords and the per-listing text, so punctuation never interferes with matching. I also verified the size filter used case-insensitive substring matching (not exact match), which the generated code initially did with `item["size"].lower() == size.lower()` — I changed it to `size_lower in item["size"].lower()` so "M" correctly matches "S/M" and "XL (fits oversized)".

### Instance 2 — Implementing the planning loop in `agent.py`

**What I directed the AI to do:** I gave Claude the full ASCII architecture diagram from planning.md and the Planning Loop section describing the exact conditional branches (if empty results → set error and return; else → set selected_item and continue). I asked it to implement `run_agent()` using the Groq LLM for query parsing, returning the parsed result as JSON.

**What I reviewed and revised:** The generated `run_agent()` called `suggest_outfit` even when `search_results` was empty — it had the branch check but then continued past it. I moved the `return session` inside the `if not session["search_results"]:` block to fix the early exit. I also found the query parser didn't strip markdown code fences from the LLM's JSON response (Groq sometimes wraps JSON in ` ```json ``` ` blocks), so I added a `re.sub` to strip those before `json.loads()`. I tested both fixes with the no-results CLI test case in `agent.py`.
