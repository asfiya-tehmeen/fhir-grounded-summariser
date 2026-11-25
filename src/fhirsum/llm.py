"""LLM backends behind one interface: complete(system, user) -> text.

- groq      : free tier, OpenAI-compatible HTTP (same as the sibling projects). Use on SYNTHETIC data.
- ollama    : local model, nothing leaves the machine. Use on MIMIC data if you prefer not to send it out.
- anthropic : Claude via the official SDK (optional extra: pip install -e ".[anthropic]").
- mock      : TEST DOUBLE that imitates a model with known error patterns. Never report its numbers as results.

All real backends go through an on-disk cache (data/cache/llm) so evaluation reruns are free and reproducible."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx

CACHE_DIR = Path(os.environ.get("FHIRSUM_CACHE", "data/cache/llm"))
USAGE_LOG = CACHE_DIR.parent / "usage.jsonl"


class QuotaExhausted(RuntimeError):
    """Daily quota hit: stop the run cleanly (cached calls are kept, rerun resumes for free)."""


def log_usage(**kw):
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time(), 1), **kw}) + "\n")


def load_env(path=".env"):
    try:
        for line in open(path, encoding="utf-8"):
            k, _, v = line.strip().partition("=")
            if k and not k.startswith("#") and v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))
    except FileNotFoundError:
        pass


class LLM:
    name = "base"
    model = ""

    def __init__(self):
        self.tokens_in = self.tokens_out = 0
        self.calls = self.cache_hits = 0

    def _call(self, system: str, user: str) -> str:
        raise NotImplementedError

    def complete(self, system: str, user: str) -> str:
        key = hashlib.sha256(f"{self.name}|{self.model}|{system}|{user}".encode()).hexdigest()
        path = CACHE_DIR / f"{key}.json"
        if self.name != "mock" and path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))["text"]
        self.calls += 1
        text = self._call(system, user)
        if self.name != "mock":
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": self.model, "text": text}), encoding="utf-8")
        return text


class GroqLLM(LLM):
    name = "groq"

    def __init__(self, model="openai/gpt-oss-120b", base="https://api.groq.com/openai/v1"):
        super().__init__()
        load_env()
        self.key = os.environ.get("GROQ_API_KEY")
        if not self.key:
            raise SystemExit("GROQ_API_KEY is empty - put it in .env (free key: https://console.groq.com/keys)")
        self.model, self.base = model, base
        # Free tier counts prompt + max_tokens against tokens-per-minute; size the output budget to fit.
        self.tpm = int(os.environ.get("GROQ_TPM", "8000"))

    @staticmethod
    def _secs(v: str | None, default: float) -> float:
        """Parse Groq reset strings like '45.5s', '1m2.3s', '820ms'."""
        if not v:
            return default
        m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?(?:([\d.]+)ms)?", v)
        if not m:
            return default
        h, mi, s, ms = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0) + float(ms or 0) / 1000

    def _call(self, system, user):
        est_prompt = (len(system) + len(user)) // 3 + 50          # conservative chars->tokens
        max_out = max(1500, min(6000, self.tpm - est_prompt - 200))
        body = {"model": self.model, "temperature": 0, "max_tokens": max_out,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if "gpt-oss" in self.model:
            body["reasoning_effort"] = os.environ.get("GROQ_REASONING_EFFORT", "low")
        last = ""
        for attempt in range(8):
            r = httpx.post(f"{self.base}/chat/completions", timeout=180,
                           headers={"Authorization": f"Bearer {self.key}"}, json=body)
            u = r.json().get("usage", {}) if r.status_code == 200 else {}
            log_usage(provider="groq", model=self.model, status=r.status_code, attempt=attempt, max_tokens=body["max_tokens"],
                      prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                      error=None if r.status_code == 200 else r.text[:160])
            if r.status_code == 429:
                last = r.text[:300]
                if "per day" in last.lower() or "TPD" in last:
                    raise QuotaExhausted(f"Groq daily token limit reached for {self.model}: {last}")
                if "Request too large" in last:
                    # Per-request cap (e.g. OTPM: output tokens per minute). Shrink once; if the cap is below what a
                    # summary needs, stop the run instead of retrying a request that can never fit.
                    m = re.search(r"\((\w+)\): Limit (\d+)", last)
                    cap = int(m.group(2)) if m else 0
                    if m and m.group(1) == "OTPM" and body["max_tokens"] > cap >= 1500:
                        body["max_tokens"] = cap - 50; continue
                    raise QuotaExhausted(f"{self.model} per-request limit too small for a summary: {last}")
                wait = max(self._secs(r.headers.get("retry-after") and r.headers["retry-after"] + "s", 0),
                           self._secs(r.headers.get("x-ratelimit-reset-tokens"), 2 ** attempt * 3))
                time.sleep(min(90, wait + 1)); continue
            if r.status_code == 400 and "json_validate_failed" in r.text:
                body.pop("response_format", None); last = r.text[:300]; continue   # retry without JSON mode
            if r.status_code >= 400:
                raise RuntimeError(f"Groq {r.status_code}: {r.text[:400]}")
            j = r.json(); u = j.get("usage", {})
            self.tokens_in += u.get("prompt_tokens", 0); self.tokens_out += u.get("completion_tokens", 0)
            return j["choices"][0]["message"].get("content") or ""
        raise RuntimeError(f"Groq rate limit: retries exhausted ({last})")


class OllamaLLM(LLM):
    name = "ollama"

    def __init__(self, model="qwen2.5:14b", base=None):
        super().__init__()
        load_env()
        self.model, self.base = model, base or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def _call(self, system, user):
        r = httpx.post(f"{self.base}/api/chat", timeout=600,
                       json={"model": self.model, "stream": False, "format": "json", "options": {"temperature": 0},
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        j = r.json()
        self.tokens_in += j.get("prompt_eval_count", 0); self.tokens_out += j.get("eval_count", 0)
        return j["message"]["content"]


class AnthropicLLM(LLM):
    name = "anthropic"

    def __init__(self, model="claude-opus-5-5", effort="medium"):
        super().__init__()
        load_env()
        import anthropic  # optional dependency
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model, self.effort = model, effort

    def _call(self, system, user):
        # Server-side refusal fallback is on by default for this model family.
        resp = self.client.beta.messages.create(
            model=self.model, max_tokens=16000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"model refused: {getattr(resp, 'stop_details', None)}")
        self.tokens_in += resp.usage.input_tokens; self.tokens_out += resp.usage.output_tokens
        return "".join(b.text for b in resp.content if b.type == "text")


class MockLLM(LLM):
    """TEST DOUBLE. Builds claims from the prompt's record lines and deliberately injects the error types
    the verifier must catch (wrong value, invented handle, wrong trend, stray number). It also 'obeys'
    un-quarantined injected instructions so the red-team harness has something to detect.
    Its numbers show the harness works; they are NOT model results."""
    name = "mock"
    model = "mock"

    def _call(self, system, user):
        if user.startswith("Some claims failed"):
            items = json.loads(user[user.index("REJECTED:\n") + 10:user.index("\nEND REJECTED")])
            fixed = []
            for i, it in enumerate(items):
                c = it["claim"]
                if i % 2 == 0 and c.get("_orig_value") is not None:
                    c["value"] = c.pop("_orig_value"); c["text"] = c.pop("_orig_text", c["text"])
                    fixed.append(c)
            return json.dumps({"claims": fixed})
        return json.dumps({"claims": self._claims(user)})

    def _claims(self, user: str) -> list[dict]:
        lines = [l for l in user.splitlines() if re.match(r"^(PT|[A-Z]+-\d+) \| ", l)]
        notes = re.findall(r'<untrusted_note handle="([^"]+)"[^>]*>\n(.*?)\n</untrusted_note>', user, re.S)
        suppressed = set()
        for _, txt in notes:
            for m in re.finditer(r"do not mention (\w+)", txt, re.I):
                suppressed.add(m.group(1).lower())
            if re.search(r"patient has no allerg", txt, re.I):
                suppressed.add("__allergies__")
        claims, labs = [], {}
        n = 0
        for l in lines:
            parts = [p.strip() for p in l.split("|")]
            h, typ = parts[0], parts[1]
            if any(s in l.lower() for s in suppressed):
                continue
            n += 1
            if typ == "Patient":
                age = int(re.search(r"age=(\d+)", l).group(1)) if "age=" in l and "age=None" not in l else None
                claims.append({"section": "Patient", "kind": "demographic", "text": f"{age}-year-old patient.", "refs": ["PT"], "value": age})
            elif typ == "Condition" and "clinicalStatus=active" in l:
                claims.append({"section": "Active problems", "kind": "condition", "text": parts[2], "refs": [h], "status": "active"})
            elif typ in ("MedicationRequest", "MedicationStatement") and "status=active" in l:
                claims.append({"section": "Medications", "kind": "medication", "text": f"Taking {parts[2]}.", "refs": [h], "status": "active"})
            elif typ == "AllergyIntolerance" and "__allergies__" not in suppressed:
                claims.append({"section": "Allergies", "kind": "allergy", "text": f"Allergy: {parts[2]}.", "refs": [h]})
            elif typ == "Observation":
                val, unit = parts[3].split(" ", 1) if " " in parts[3] else (parts[3], "")
                labs.setdefault(parts[2], []).append((h, float(val), unit, parts[4]))
        if not any(c["kind"] == "allergy" for c in claims) and "__allergies__" not in suppressed:
            claims.append({"section": "Allergies", "kind": "absence", "text": "No allergy records found.", "absent_type": "AllergyIntolerance", "refs": []})
        if "__allergies__" in suppressed:
            claims.append({"section": "Allergies", "kind": "absence", "text": "No known allergies.", "absent_type": "AllergyIntolerance", "refs": []})
        for i, (name, pts) in enumerate(labs.items()):
            h, v, u, d = pts[-1]
            c = {"section": "Recent labs and trends", "kind": "lab_value", "text": f"{name} {v:g} {u} on {d}.", "refs": [h], "value": v, "unit": u, "date": d}
            if i % 4 == 1:   # planted error: wrong value in both field and text
                c["_orig_value"], c["_orig_text"] = v, c["text"]
                c["value"] = round(v * 1.3 + 1, 1); c["text"] = f"{name} {c['value']:g} {u} on {d}."
            claims.append(c)
            if len(pts) >= 2:
                vals = [p[1] for p in pts]
                trend = "increasing" if vals[-1] > vals[0] * 1.05 else "decreasing" if vals[-1] < vals[0] * 0.95 else "stable"
                if i % 3 == 2:   # planted temporal error
                    trend = {"increasing": "decreasing", "decreasing": "increasing", "stable": "increasing"}[trend]
                claims.append({"section": "Recent labs and trends", "kind": "lab_trend", "text": f"{name} {trend} over the last year.",
                               "refs": [p[0] for p in pts], "trend": trend})
        if claims:   # planted error: invented citation
            claims.append({"section": "Active problems", "kind": "condition", "text": "History of atrial fibrillation.", "refs": ["PROB-999"]})
        return claims


def make_llm(provider: str, model: str | None = None) -> LLM:
    if provider == "groq":
        return GroqLLM(model or "openai/gpt-oss-120b")
    if provider == "ollama":
        return OllamaLLM(model or "qwen2.5:14b")
    if provider == "anthropic":
        return AnthropicLLM(model or "claude-opus-5-5")
    if provider == "mock":
        return MockLLM()
    raise SystemExit(f"unknown provider {provider}")


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise
