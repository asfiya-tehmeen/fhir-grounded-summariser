"""Turn a Summary into Markdown (CLI) or JSON (web UI). Only verified claims are shown as summary text;
dropped claims are listed separately with reasons so nothing disappears silently."""
from __future__ import annotations

from .prompts import SECTIONS
from .record import PatientRecord
from .summarise import Summary

DISCLAIMER = ("Research prototype on synthetic / de-identified data. Not clinically validated. "
              "Not medical advice. Always check the source record.")


def _ordered_sections(s: Summary) -> list[tuple[str, list]]:
    order = SECTIONS.get(s.summary_type, [])
    groups: dict[str, list] = {}
    for v in s.kept:
        groups.setdefault(v.claim.section or "Other", []).append(v)
    names = [n for n in order if n in groups] + [n for n in groups if n not in order]
    return [(n, groups[n]) for n in names]


def to_markdown(rec: PatientRecord, s: Summary) -> str:
    out = [f"# {s.summary_type} summary ({s.mode})", f"_{DISCLAIMER}_", ""]
    if s.checks:
        out.append("## System checks (computed by code, not the model)")
        out += [f"- **{c.kind}**: {c.message} {' '.join(f'[{r}]' for r in c.refs)}" for c in s.checks]
        out.append("")
    for name, vs in _ordered_sections(s):
        out.append(f"## {name}")
        for v in vs:
            tag = " _(added by completeness check)_" if v.claim.id in s.backfilled_ids else ""
            out.append(f"- {v.claim.text}{tag} " + " ".join(f"[{r}]" for r in v.resolved_refs))
        out.append("")
    if s.dropped:
        out.append(f"## Removed by verifier ({len(s.dropped)})")
        out += [f"- ~~{v.claim.text}~~ - {'; '.join(v.reasons)}" for v in s.dropped]
    out.append(f"\n_latency {s.latency_s}s, tokens in/out {s.tokens_in}/{s.tokens_out}_")
    return "\n".join(out)


def to_json(rec: PatientRecord, s: Summary) -> dict:
    def vj(v):
        d = v.claim.model_dump(exclude_none=True)
        d["resolved_refs"] = v.resolved_refs
        d["reasons"] = v.reasons
        d["origin"] = "code" if v.claim.id in s.backfilled_ids or s.mode == "template" else "model"
        return d
    used = {r for v in s.kept + s.dropped for r in v.resolved_refs} | {r for c in s.checks for r in c.refs}
    return {
        "summary_type": s.summary_type, "mode": s.mode, "disclaimer": DISCLAIMER,
        "patient": {"id": rec.patient.get("id"), "gender": rec.patient.get("gender"), "age": rec.age(), "source": rec.source},
        "sections": [{"name": n, "claims": [vj(v) for v in vs]} for n, vs in _ordered_sections(s)],
        "dropped": [vj(v) for v in s.dropped],
        "checks": [{"kind": c.kind, "message": c.message, "refs": c.refs} for c in s.checks],
        "resources": {r: rec.resources[r] for r in used if r in rec.resources},
        "stats": {"kept": len(s.kept), "backfilled": len(s.backfilled_ids), "dropped": len(s.dropped), "malformed": s.malformed,
                  "latency_s": s.latency_s, "tokens_in": s.tokens_in, "tokens_out": s.tokens_out},
    }
