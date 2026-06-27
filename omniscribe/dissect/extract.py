"""Content extraction: turn raw text into a structured learning schema.

Two paths produce the *same* schema:
  * ``extract_with_llm``  — Anthropic Claude (rich, accurate). Used when a key is present.
  * ``extract_heuristic`` — pure-Python fallback (always works offline).

Schema::

    {
      "title", "summary", "language",
      "concepts":     [{"name", "explanation", "examples": [..]}],
      "applications":  [str, ..],
      "keyTakeaways":  [str, ..],
      "mindmap":      {"central", "branches": [{"name", "subbranches": [..]}]},
      "infographic":  {"stats": [{"label", "value"}], "mainPoints": [{"title", "description"}]},
      "flashcards":    [{"question", "answer"}],
      "quiz":          [{"question", "options": [..], "answer_index": int}]
    }
"""
from __future__ import annotations

import json
import re

from .. import config


def detect_language(text: str) -> str:
    arabic = len(re.findall(r"[؀-ۿ]", text))
    if arabic > max(1, len(re.sub(r"\s", "", text))) * 0.2:
        return "ar"
    # crude French hint
    if re.search(r"\b(le|la|les|des|une|est|être|avec|pour)\b", text.lower()):
        latin = len(re.findall(r"[a-zA-Zà-ÿ]", text))
        if latin and len(re.findall(r"[éèêàçùâîô]", text)) > latin * 0.01:
            return "fr"
    return "en"


# --------------------------------------------------------------------------- LLM
_SCHEMA_INSTRUCTION = """You are an expert instructional designer. Analyse the provided
content and produce study materials. Respond with a SINGLE JSON object ONLY (no prose,
no markdown fences) with EXACTLY these keys:

{
  "title": "concise descriptive title",
  "summary": "2-4 sentence overview",
  "language": "en | ar | fr (the dominant language of the content)",
  "concepts": [{"name": "...", "explanation": "1-3 sentences", "examples": ["..."]}],
  "applications": ["practical application", "..."],
  "keyTakeaways": ["memorable takeaway", "..."],
  "mindmap": {"central": "topic", "branches": [{"name": "branch", "subbranches": ["sub", "..."]}]},
  "infographic": {"stats": [{"label": "...", "value": "..."}],
                   "mainPoints": [{"title": "...", "description": "..."}]},
  "flashcards": [{"question": "...", "answer": "..."}],
  "quiz": [{"question": "...", "options": ["A","B","C","D"], "answer_index": 0}]
}

Rules: 4-7 concepts, 6-12 flashcards, 4-6 quiz questions, 3-6 mindmap branches.
Write all human-readable values in the SAME language as the content.
Keep values plain text (no markdown). Output ONLY the JSON object."""


def _strip_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    # Grab the outermost {...} if extra text slipped in.
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]
    return raw.strip()


def _balance_json(s: str) -> str:
    """Close an unterminated/truncated JSON fragment, respecting strings and nesting order."""
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    out = s
    if in_str:
        out += '"'
    # Drop a dangling trailing comma / whitespace before appending closers.
    out = re.sub(r",\s*$", "", out.rstrip())
    for opener in reversed(stack):
        out += "}" if opener == "{" else "]"
    return out


def _loads_lenient(raw: str) -> dict:
    """Parse JSON tolerantly — smaller free models sometimes emit slightly malformed JSON."""
    s = _strip_json(raw)
    candidates = [
        s,
        re.sub(r",\s*([}\]])", r"\1", s),          # strip trailing commas
        _balance_json(re.sub(r",\s*([}\]])", r"\1", s)),  # close truncated structures
    ]
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    # last resort: trim from the end to the last bracket, then balance
    for cut in range(len(s) - 1, max(0, len(s) - 6000), -1):
        if s[cut] in "}]\"":
            try:
                return json.loads(_balance_json(s[: cut + 1]))
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("could not repair JSON", s, 0)


def extract_with_llm(text: str, model: str | None = None) -> tuple[dict, str]:
    """Extract via the multi-provider LLM chain. Returns (schema, provider_name)."""
    from . import llm

    # Keep prompts bounded; very long inputs are truncated to a generous window.
    content = text if len(text) <= 60000 else text[:60000]
    raw, provider = llm.complete(
        _SCHEMA_INSTRUCTION, f"CONTENT TO ANALYSE:\n\n{content}",
        max_tokens=config.LLM_MAX_TOKENS,
    )
    data = _loads_lenient(raw)
    return normalize_schema(data, text), provider


# --------------------------------------------------------------------- heuristic
def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟।])\s+|\n{2,}", text)
    return [p.strip() for p in parts if len(p.strip()) > 3]


def _paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n\s*\n", text)
    return [p.strip().replace("\n", " ") for p in paras if len(p.strip()) > 30]


def extract_heuristic(text: str) -> dict:
    text = text.strip()
    lang = detect_language(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first = lines[0] if lines else "Study Notes"
    # Treat a short, terminator-free first line as a heading and exclude it from the body
    # so it doesn't pollute sentence-derived flashcards/summaries.
    is_heading = len(first) <= 90 and not re.search(r"[.!?؟]\s*$", first)
    body = "\n".join(lines[1:]) if (is_heading and len(lines) > 1) else text

    sents = _sentences(body)
    paras = _paragraphs(body)
    if len(paras) < 2:  # prose with single-newline breaks -> use sentences as units
        paras = sents or paras

    # Title: a clean heading if we have one, otherwise a concise phrase from the opener.
    if is_heading:
        title = first[:90]
    else:
        opener = (sents[0] if sents else first)
        words = opener.split()
        title = (opener if len(opener) <= 60 else " ".join(words[:8]) + "…")[:90]

    summary = " ".join(sents[:3])[:600] if sents else title

    concepts = []
    for para in paras[:6]:
        words = para.split()
        name = " ".join(words[:6]) + ("…" if len(words) > 6 else "")
        concepts.append({"name": name, "explanation": para[:400], "examples": []})

    takeaways = []
    for para in paras[:6]:
        s = _sentences(para)
        if s:
            takeaways.append(s[0][:200])
    if not takeaways:
        takeaways = sents[:5]

    # Flashcards: turn "X is/are Y" or "X: Y" patterns into Q/A, else cloze deletions.
    flashcards = []
    seen_q = set()

    def add_card(q, a):
        q, a = q.strip(), a.strip().rstrip(".")
        key = q.lower()
        if q and a and key not in seen_q and len(a) > 1:
            seen_q.add(key)
            flashcards.append({"question": q, "answer": a})

    for s in sents:
        m = re.match(r"(.{4,60}?)\s+(?:is|are|means|refers to|est|sont)\s+(.{4,})", s, re.I)
        if m:
            add_card(f"What is {m.group(1).strip()}?", m.group(2))
        elif ":" in s and 2 <= len(s.split(":", 1)[0].split()) <= 8:
            k, v = s.split(":", 1)
            add_card(f"What is {k.strip()}?", v)
        if len(flashcards) >= 10:
            break
    if len(flashcards) < 4:
        for s in sents[:10]:
            words = s.split()
            if len(words) >= 6:
                idx = max(range(len(words)), key=lambda i: len(words[i]))
                ans = words[idx].strip(".,;:()")
                blanked = words.copy()
                blanked[idx] = "_____"
                add_card("Fill in the blank: " + " ".join(blanked), ans)
            if len(flashcards) >= 6:
                break

    branches = [{"name": c["name"], "subbranches": []} for c in concepts[:6]]
    mindmap = {"central": title, "branches": branches}

    words_total = len(text.split())
    infographic = {
        "stats": [
            {"label": "Words", "value": str(words_total)},
            {"label": "Concepts", "value": str(len(concepts))},
            {"label": "Read time", "value": f"{max(1, round(words_total / 200))} min"},
        ],
        "mainPoints": [{"title": c["name"], "description": c["explanation"][:160]} for c in concepts[:4]],
    }

    quiz = []
    for fc in flashcards[:4]:
        quiz.append({
            "question": fc["question"],
            "options": [fc["answer"][:60], "None of the above", "Not specified", "All of the above"],
            "answer_index": 0,
        })

    return normalize_schema({
        "title": title,
        "summary": summary,
        "language": lang,
        "concepts": concepts,
        "applications": [],
        "keyTakeaways": takeaways,
        "mindmap": mindmap,
        "infographic": infographic,
        "flashcards": flashcards,
        "quiz": quiz,
    }, text)


# --------------------------------------------------------------------- normalise
def normalize_schema(data: dict, source_text: str = "") -> dict:
    """Coerce any partial/garbled schema into a complete, well-typed one."""
    def s(x, default=""):
        return x if isinstance(x, str) else (default if x is None else str(x))

    def lst(x):
        return x if isinstance(x, list) else ([] if x is None else [x])

    out = {
        "title": s(data.get("title"), "Study Notes") or "Study Notes",
        "summary": s(data.get("summary")),
        "language": s(data.get("language")) or (detect_language(source_text) if source_text else "en"),
        "concepts": [],
        "applications": [s(a) for a in lst(data.get("applications")) if s(a)],
        "keyTakeaways": [s(t) for t in lst(data.get("keyTakeaways")) if s(t)],
        "mindmap": {"central": "", "branches": []},
        "infographic": {"stats": [], "mainPoints": []},
        "flashcards": [],
        "quiz": [],
    }

    for c in lst(data.get("concepts")):
        if isinstance(c, dict):
            out["concepts"].append({
                "name": s(c.get("name")),
                "explanation": s(c.get("explanation")),
                "examples": [s(e) for e in lst(c.get("examples")) if s(e)],
            })

    mm = data.get("mindmap") if isinstance(data.get("mindmap"), dict) else {}
    out["mindmap"]["central"] = s(mm.get("central")) or out["title"]
    for b in lst(mm.get("branches")):
        if isinstance(b, dict):
            out["mindmap"]["branches"].append({
                "name": s(b.get("name")),
                "subbranches": [s(x) for x in lst(b.get("subbranches")) if s(x)],
            })
        elif s(b):
            out["mindmap"]["branches"].append({"name": s(b), "subbranches": []})

    ig = data.get("infographic") if isinstance(data.get("infographic"), dict) else {}
    for st in lst(ig.get("stats")):
        if isinstance(st, dict):
            out["infographic"]["stats"].append({"label": s(st.get("label")), "value": s(st.get("value"))})
    for mp in lst(ig.get("mainPoints")):
        if isinstance(mp, dict):
            out["infographic"]["mainPoints"].append(
                {"title": s(mp.get("title")), "description": s(mp.get("description"))}
            )

    for fc in lst(data.get("flashcards")):
        if isinstance(fc, dict) and (s(fc.get("question")) or s(fc.get("answer"))):
            out["flashcards"].append({"question": s(fc.get("question")), "answer": s(fc.get("answer"))})

    for q in lst(data.get("quiz")):
        if isinstance(q, dict) and s(q.get("question")):
            opts = [s(o) for o in lst(q.get("options")) if s(o)][:6]  # cap options
            if len(opts) >= 2:
                try:
                    ai = int(q.get("answer_index", 0))
                except (ValueError, TypeError):
                    ai = 0
                out["quiz"].append({"question": s(q.get("question")), "options": opts,
                                    "answer_index": max(0, min(ai, len(opts) - 1))})

    return out


def extract(text: str, use_llm: bool = True, model: str | None = None) -> tuple[dict, str]:
    """Return (schema, method). Tries the LLM provider chain, falls back to heuristic.

    ``method`` is the provider name (e.g. "gemini", "pollinations") on success, or
    "heuristic" / "heuristic-fallback" when the offline extractor is used.
    """
    from . import llm

    if use_llm and llm.available_providers():
        try:
            schema, provider = extract_with_llm(text, model=model)
            schema = _fill_gaps(schema, text)  # complete any sections a model omitted/truncated
            return schema, provider
        except Exception as exc:  # network / parse / quota -> graceful fallback
            return {**extract_heuristic(text), "_llm_error": str(exc)}, "heuristic-fallback"
    return extract_heuristic(text), "heuristic"


def _fill_gaps(schema: dict, text: str) -> dict:
    """Fill any empty sections of an LLM schema from the heuristic extractor.

    Smaller/free models sometimes omit or truncate later fields (flashcards, quiz). This
    guarantees a complete, usable set of study materials regardless of model quality.
    """
    needs = (
        not schema.get("concepts") or not schema.get("flashcards") or not schema.get("quiz")
        or not schema.get("keyTakeaways") or not schema.get("summary")
        or not schema["mindmap"]["branches"]
        or not schema["infographic"]["stats"] or not schema["infographic"]["mainPoints"]
    )
    if not needs:
        return schema
    h = extract_heuristic(text)
    for key in ("concepts", "flashcards", "quiz", "keyTakeaways", "applications"):
        if not schema.get(key):
            schema[key] = h.get(key, [])
    if not schema.get("summary"):
        schema["summary"] = h.get("summary", "")
    if not schema["mindmap"]["branches"]:
        schema["mindmap"]["branches"] = h["mindmap"]["branches"]
    if not schema["infographic"]["stats"]:
        schema["infographic"]["stats"] = h["infographic"]["stats"]
    if not schema["infographic"]["mainPoints"]:
        schema["infographic"]["mainPoints"] = h["infographic"]["mainPoints"]
    return schema
