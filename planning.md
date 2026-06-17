# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items that match a natural-language description, optional size filter, and optional price ceiling. Returns a relevance-ranked list of matching items so the agent can pick the best result.

**Input parameters:**
- `description` (str): Keywords describing what the user is looking for (e.g., "vintage graphic tee", "90s track jacket"). Used to compute a relevance score against each listing.
- `size` (str | None): Size string to filter by (e.g., "M", "S/M", "US 8"), or None to skip size filtering. Matching is case-insensitive substring match (so "M" matches "S/M" and "XL (fits oversized)").
- `max_price` (float | None): Maximum price inclusive (e.g., 30.0), or None to skip price filtering. Listings with price > max_price are excluded before scoring.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str — one of tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str — excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str — depop/thredUp/poshmark). Returns an empty list `[]` if no listings match — never raises an exception.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to a human-readable message like "No listings found for '[query]'. Try a broader description, a different size, or a higher price limit." It returns the session immediately without calling `suggest_outfit` or `create_fit_card`. The user sees the error in the first output panel.

---

### Tool 2: suggest_outfit

**What it does:**
Given the thrifted item the user is considering and the user's existing wardrobe, calls the LLM to suggest 1–2 complete outfit combinations using named pieces from the wardrobe. If the wardrobe is empty, returns general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A listing dict — the item the user is considering buying. Relevant fields used in the prompt: `title`, `description`, `category`, `style_tags`, `colors`, `condition`.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has: `id`, `name`, `category`, `colors`, `style_tags`, `notes`. May be an empty list — handled gracefully.

**What it returns:**
A non-empty string containing 1–2 outfit suggestions. When the wardrobe is populated, suggestions reference specific named items (e.g., "pair with your baggy straight-leg jeans and chunky white sneakers"). When the wardrobe is empty, the string is general styling advice about what kinds of pieces work well with the item and what aesthetic it suits.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty the tool does not crash — it calls the LLM with an empty-wardrobe prompt and returns general advice. If the LLM call itself fails (network error, API error), the tool catches the exception and returns a fallback string: "Unable to generate outfit suggestion right now. The item is a [category] — try pairing it with complementary basics."

---

### Tool 3: create_fit_card

**What it does:**
Takes the outfit suggestion and the listing dict and asks the LLM to generate a short (2–4 sentence) shareable caption in the style of an OOTD Instagram post — casual, specific, and authentic. Uses a higher temperature (1.1) so the output varies across calls.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Must be non-empty; if it is empty or whitespace-only, the tool returns an error message string without calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item. Used to pull `title`, `price`, `platform`, and `condition` into the caption prompt.

**What it returns:**
A 2–4 sentence string formatted as a social-media caption. Mentions the item name, price, and platform naturally once each. Captures the outfit vibe in specific terms. Varies meaningfully across different inputs. If `outfit` is empty/whitespace, returns the string: "Cannot generate a fit card without an outfit suggestion. Please provide outfit details."

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace the tool returns the error string above without hitting the LLM. If the LLM call fails, the tool catches the exception and returns: "Fit card generation failed — but here's the item: [title] for $[price] on [platform]."

---

### Additional Tools (if any)

No additional tools beyond the required three.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop in `run_agent()` uses a strict conditional sequence controlled by the session state dict. Here is the exact branch logic:

1. **Initialize session** — call `_new_session(query, wardrobe)`. All output fields start as None.

2. **Parse the query** — send the raw query to the Groq LLM with a JSON-extraction prompt asking it to return `{"description": str, "size": str|null, "max_price": float|null}`. Store the parsed result in `session["parsed"]`. If JSON parsing fails, fall back to using the full query as `description` with `size=None` and `max_price=None`.

3. **Call `search_listings`** — pass `session["parsed"]["description"]`, `session["parsed"]["size"]`, and `session["parsed"]["max_price"]`. Store the result in `session["search_results"]`.
   - **Branch A (empty results):** if `len(session["search_results"]) == 0`, set `session["error"] = "No listings found for '{description}'. Try a broader description, remove the size filter, or increase your price limit."` and **return session immediately**. `suggest_outfit` and `create_fit_card` are never called.
   - **Branch B (results found):** set `session["selected_item"] = session["search_results"][0]` and continue.

4. **Call `suggest_outfit`** — pass `session["selected_item"]` and `session["wardrobe"]`. Store the return value in `session["outfit_suggestion"]`. (This tool handles its own empty-wardrobe case internally.)

5. **Call `create_fit_card`** — pass `session["outfit_suggestion"]` and `session["selected_item"]`. Store the return value in `session["fit_card"]`.

6. **Return session** — `session["error"]` remains None on the happy path. Callers check `session["error"]` first.

The agent never calls `suggest_outfit` or `create_fit_card` when `search_results` is empty. It also never calls `create_fit_card` if `outfit_suggestion` is somehow empty (guarded inside `create_fit_card` itself, which returns an error string rather than crashing).

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single session dict initialized by `_new_session()` at the start of each call to `run_agent()`. The dict has these keys:

| Key | Type | Set when | Used by |
|-----|------|----------|---------|
| `query` | str | initialization | query parsing step |
| `parsed` | dict | after LLM parse | `search_listings` call |
| `search_results` | list[dict] | after `search_listings` | branch check, `selected_item` selection |
| `selected_item` | dict or None | after branch B | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | initialization | `suggest_outfit` |
| `outfit_suggestion` | str or None | after `suggest_outfit` | `create_fit_card` |
| `fit_card` | str or None | after `create_fit_card` | returned to caller / UI |
| `error` | str or None | on early termination | returned to caller / UI |

No data is passed by re-prompting the user. `selected_item` from step 3 is the exact same dict object passed into `suggest_outfit` in step 4. `outfit_suggestion` from step 4 is the exact same string passed into `create_fit_card` in step 5. The session dict is returned at the end so the caller (Gradio `handle_query`) can read every field.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the description/size/price combination — returns `[]` | Agent sets `session["error"]` to "No listings found for '[description]'. Try a broader description, remove the size filter, or raise your price limit." and returns immediately. `suggest_outfit` and `create_fit_card` are never called. User sees this message in the first output panel. |
| `suggest_outfit` | `wardrobe["items"]` is empty (new user with no wardrobe entered) | Tool detects the empty list before calling the LLM and uses a different prompt asking for general styling advice. Returns a non-empty string such as "Since your wardrobe is empty, here's how to style this piece: …" — never returns an empty string or raises an exception. |
| `create_fit_card` | `outfit` argument is empty or whitespace-only | Tool returns the error string "Cannot generate a fit card without an outfit suggestion. Please provide outfit details." without calling the LLM at all. This prevents an unhelpful or malformed caption. |

---

## Architecture

```
User query (natural language)
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│                        Planning Loop                         │
│                       run_agent()                            │
│                                                              │
│  Step 1: _new_session(query, wardrobe)                       │
│         → session dict initialized                           │
│                                                              │
│  Step 2: LLM parse query                                     │
│         → session["parsed"] = {description, size, max_price} │
│                │                                             │
│  Step 3: search_listings(description, size, max_price)       │
│         → session["search_results"]                          │
│                │                                             │
│         results == [] ?                                      │
│          YES ──────────────────────────────────────────────► │
│          │   session["error"] = "No listings found…"         │
│          │   return session  (early exit)                    │
│          │                                                   │
│          NO                                                  │
│          │                                                   │
│         session["selected_item"] = search_results[0]        │
│                │                                             │
│  Step 4: suggest_outfit(selected_item, wardrobe)             │
│         → session["outfit_suggestion"]                       │
│         (wardrobe empty? → general advice branch inside tool)│
│                │                                             │
│  Step 5: create_fit_card(outfit_suggestion, selected_item)   │
│         → session["fit_card"]                                │
│         (outfit empty? → error string branch inside tool)    │
│                │                                             │
│  Step 6: return session  (session["error"] = None)           │
└──────────────────────────────────────────────────────────────┘
        │                               │
        ▼                               ▼
  Happy-path session:            Error-path session:
  selected_item = {...}          error = "No listings found…"
  outfit_suggestion = "…"        selected_item = None
  fit_card = "…"                 outfit_suggestion = None
  error = None                   fit_card = None
        │
        ▼
  Gradio handle_query()
  → (listing_text, outfit_text, fitcard_text) displayed in 3 panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **Tool 1 (`search_listings`):** I used Claude and provided the Tool 1 spec block from this planning.md (inputs with types, return value description including all listing fields, and the failure mode stating it returns `[]` and never raises). I asked Claude to implement the function using `load_listings()` and to score listings by counting how many description keywords appear in the listing's title, description, style_tags, colors, category, and brand fields. Before running the generated code I verified: (a) it calls `load_listings()`, not a custom file reader; (b) it applies both filters before scoring; (c) it returns `[]` when no items score above 0; (d) the size filter is case-insensitive substring match. I then tested with 3 queries (graphic tee, track jacket, impossible ballgown query).

- **Tool 2 (`suggest_outfit`):** I provided Claude the Tool 2 spec block plus the wardrobe schema from `data/wardrobe_schema.json` (so it knew the exact field names). I asked it to implement the function using the Groq client initialized with `_get_groq_client()`, model `llama-3.3-70b-versatile`. Before using the generated code I verified: (a) it checks `wardrobe["items"]` for emptiness before building the prompt; (b) the populated-wardrobe prompt names specific wardrobe items rather than just saying "your wardrobe"; (c) the empty-wardrobe prompt explicitly requests general styling advice. I tested with both `get_example_wardrobe()` and `get_empty_wardrobe()`.

- **Tool 3 (`create_fit_card`):** I provided Claude the Tool 3 spec block, emphasizing the casual caption style and the requirement that output vary across runs. I asked it to use `temperature=1.1` and to mention item name, price, and platform naturally. Before using the code I verified: (a) the empty-outfit guard returns a string without hitting the LLM; (b) the prompt explicitly says "do not write a product description — write a real OOTD caption"; (c) temperature is set higher than the default. I ran the same input 3 times and confirmed the outputs differed.

**Milestone 4 — Planning loop and state management:**

- I provided Claude the Architecture diagram above and the Planning Loop + State Management sections, and asked it to implement `run_agent()` in `agent.py`. I specified that it must: use the Groq LLM to parse the query into JSON, branch on empty `search_results`, store each tool's result in the named session key, and return the session dict. Before using the generated code I verified: (a) it does not call `suggest_outfit` unconditionally — there is an `if not session["search_results"]: return session` branch; (b) `session["selected_item"]` is set to `session["search_results"][0]` before `suggest_outfit` is called; (c) the session dict is returned in all branches. I then tested with a happy-path query and the deliberate no-results query from the CLI test in `agent.py`.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent sends the query to the Groq LLM for parsing. The LLM extracts: `{"description": "vintage graphic tee", "size": null, "max_price": 30.0}`. The agent stores this in `session["parsed"]` and calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`.

The tool loads all 40 listings, filters out any priced above $30.00, then scores the remaining listings by counting how many of the words "vintage", "graphic", "tee" appear across each listing's title, description, style_tags, colors, and category. It finds matches including:
- lst_006 "Graphic Tee — 2003 Tour Bootleg Style" ($24, tags: graphic tee, vintage, grunge, streetwear, band tee) → score 5
- lst_033 "Vintage Band Tee — Faded Grey" ($19, tags: vintage, grunge, band tee, graphic tee) → score 4
- lst_002 "Y2K Baby Tee — Butterfly Print" ($18, tags: y2k, vintage) → score 2

The tool returns these sorted by score. The agent stores the list in `session["search_results"]`, confirms it is non-empty, and sets `session["selected_item"] = results[0]` (the Graphic Tee at $24).

**Step 2:**
The agent calls `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`. The wardrobe has 10 items (baggy jeans, khaki trousers, white tank, grey crewneck, black hoodie, denim jacket, chunky sneakers, combat boots, brown belt, black bag).

The tool builds a prompt listing all wardrobe items by name and asks the LLM to suggest 1–2 outfits using the graphic tee and specific named wardrobe pieces. The LLM responds:

"Outfit 1: Pair this Graphic Tee with your baggy straight-leg jeans (dark wash) and chunky white sneakers for a classic 90s streetwear look. Tuck the front corner slightly for shape and add the black crossbody bag. Outfit 2: Layer the tee under your vintage black denim jacket over wide-leg khaki trousers and combat boots for a grungier take — roll the sleeves once."

The agent stores this string in `session["outfit_suggestion"]`.

**Step 3:**
The agent calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`. The tool builds a prompt with the item details (title: "Graphic Tee — 2003 Tour Bootleg Style", price: $24, platform: depop, condition: good) and the outfit text, and asks the LLM for a 2–4 sentence OOTD caption at temperature 1.1.

The LLM returns something like: "found this faded bootleg tee on depop for $24 and it literally fits like a dream 🖤 baggy dark wash jeans + chunky sneakers = the only formula i know. this is my entire personality."

The agent stores this in `session["fit_card"]`.

**Final output to user:**
The Gradio interface displays three panels:
- **Top listing found:** "Graphic Tee — 2003 Tour Bootleg Style | $24.00 | depop | Size: L | Condition: good | Style: graphic tee, vintage, grunge, streetwear, band tee"
- **Outfit idea:** The full `outfit_suggestion` string from Step 2.
- **Your fit card:** The caption from Step 3.

**Error path (no results):** If the query were "designer ballgown size XXS under $5", `search_listings` would return `[]`. The agent sets `session["error"] = "No listings found for 'designer ballgown'. Try a broader description, remove the size filter, or raise your price limit."` and returns immediately. The UI displays this error in the first panel; the other two panels are empty.
