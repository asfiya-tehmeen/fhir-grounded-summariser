"""Free-text hygiene for clinical notes before they reach the model.

Two layers:
1. Quarantine: sentences that look like instructions to an AI (not clinical content) are withheld and
   replaced with a marker; the clinician sees a safety check saying so.
2. Isolation: remaining note text is wrapped as untrusted data in the prompt (see prompts.py).
The red-team suite measures each layer separately (sanitiser on/off)."""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"\bignore (all |any )?(the )?(previous|prior|above|earlier)\b",
    r"\bdisregard (all |any )?(the )?(previous|prior|above|earlier|instructions?)\b",
    r"\b(system|assistant|developer)\s*(prompt|message|instruction)s?\b",
    r"\byou are (now )?(an?|the) (ai|assistant|model|language model|chatbot)\b",
    r"\b(do not|don't|never) (mention|include|report|list|say|state)\b",
    r"\b(omit|remove|hide|suppress) (the |any |all )?(allerg|medication|warfarin|diagnos|lab|result)",
    r"\b(state|say|report|write) (that )?the patient (has|have) no\b",
    r"\bnew instructions?\b",
    r"\bas an ai\b",
    r"\bsummar(y|iser|izer|iser's)\b.*\b(must|should) (say|state|read)\b",
    r"</?\s*(system|instructions?|prompt|untrusted_note)\s*>",
]
_RX = [re.compile(p, re.I) for p in INJECTION_PATTERNS]
_SENT = re.compile(r"(?<=[.!?\n])\s+")


def find_injections(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if any(rx.search(s) for rx in _RX)]


def quarantine(text: str) -> tuple[str, list[str]]:
    spans = find_injections(text)
    clean = text
    for s in spans:
        clean = clean.replace(s, "[WITHHELD: instruction-like text removed by sanitiser]")
    return clean, spans


def neutralise_delimiters(text: str) -> str:
    """Stop note text from closing our data wrapper tags."""
    return re.sub(r"<\s*/?\s*untrusted_note[^>]*>", "[tag removed]", text, flags=re.I)
