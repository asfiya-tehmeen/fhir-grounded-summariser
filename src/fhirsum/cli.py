"""fhirsum CLI.

  fhirsum gen-suite                         # synthetic patients + red-team traps -> data/generated
  fhirsum summarise data/generated/clean_000.json --type handoff --llm groq
  fhirsum eval --dir data/generated --llm groq [--no-sanitise] [--type patient]
  fhirsum fetch --base http://localhost:8080/fhir --patient 123 --out data/server/p123.json
  fhirsum mimic-split data/raw/mimic/.../fhir --out data/mimic
  fhirsum synthea-import data/raw/synthea/fhir --out data/synthea [--plant]
  fhirsum serve                             # http://localhost:8000 (SMART launch: /launch.html)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fhirsum")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen-suite"); g.add_argument("--out", default="data/generated"); g.add_argument("--n-clean", type=int, default=20)

    s = sub.add_parser("summarise")
    s.add_argument("path"); s.add_argument("--type", default="handoff", choices=["handoff", "medrec", "patient"])
    s.add_argument("--llm", default="groq", help="groq|anthropic|ollama|mock|template"); s.add_argument("--model")
    s.add_argument("--no-verify", action="store_true"); s.add_argument("--json", action="store_true")

    e = sub.add_parser("eval")
    e.add_argument("--dir", default="data/generated"); e.add_argument("--llm", default="none"); e.add_argument("--model")
    e.add_argument("--type", default="handoff", choices=["handoff", "medrec", "patient"])
    e.add_argument("--no-sanitise", action="store_true"); e.add_argument("--limit", type=int)
    e.add_argument("--pattern", default="*.json", help="glob inside --dir, e.g. '*_0*.json'")
    e.add_argument("--prompt", default="v1", choices=["v1", "v2"], help="system prompt version (paired experiments)")
    e.add_argument("--offline", action="store_true",
                   help="never call the API: re-score cached answers only (uncached repair rounds are skipped and counted)")
    e.add_argument("--out", help="results dir (default results/<llm>_<type>[_nosan])")

    f = sub.add_parser("fetch"); f.add_argument("--base", required=True); f.add_argument("--patient", required=True)
    f.add_argument("--token"); f.add_argument("--out", required=True)

    m = sub.add_parser("mimic-split"); m.add_argument("src"); m.add_argument("--out", default="data/mimic"); m.add_argument("--max", type=int)

    ms = sub.add_parser("mimic-scope", help="cut each MIMIC patient to their latest hospital admission")
    ms.add_argument("--src", default="data/mimic"); ms.add_argument("--out", default="data/mimic_adm")

    sy = sub.add_parser("synthea-import"); sy.add_argument("src"); sy.add_argument("--out", default="data/synthea")
    sy.add_argument("--plant", action="store_true", help="also write trap variants (injections, missing allergies)")

    sv = sub.add_parser("serve"); sv.add_argument("--port", type=int, default=8000); sv.add_argument("--host", default="127.0.0.1")

    pr = sub.add_parser("progress", help="completion of each eval stage in results/ + today's token use")
    pr.add_argument("--results", default="results")

    a = ap.parse_args(argv)

    if a.cmd == "gen-suite":
        from .synth import build_suite
        ps = build_suite(a.out, a.n_clean)
        print(f"wrote {len(ps)} bundles to {a.out}")

    elif a.cmd == "summarise":
        from .llm import make_llm
        from .record import PatientRecord
        from .render import to_json, to_markdown
        from .summarise import summarise, template_summary
        rec = PatientRecord.from_file(a.path)
        s = template_summary(rec, a.type) if a.llm == "template" else \
            summarise(rec, make_llm(a.llm, a.model), a.type, verify=not a.no_verify)
        out = json.dumps(to_json(rec, s), indent=1) if a.json else to_markdown(rec, s)
        sys.stdout.reconfigure(encoding="utf-8")
        print(out)

    elif a.cmd == "eval":
        from .evaluate import run_eval
        from .llm import make_llm
        llm = None if a.llm == "none" else make_llm(a.llm, a.model)
        if llm is not None:
            llm.offline = a.offline
        out = Path(a.out or f"results/{a.llm}_{a.type}{'_nosan' if a.no_sanitise else ''}")
        paths = sorted({p for pat in a.pattern.split(",") for p in Path(a.dir).glob(pat.strip())})
        agg = run_eval(paths, llm, a.type, sanitise=not a.no_sanitise, out_dir=out, limit=a.limit, prompt=a.prompt)
        print((out / "summary.md").read_text(encoding="utf-8"))
        if llm is not None:
            print(f"llm calls={llm.calls} cache_hits={llm.cache_hits} tokens spent now in/out={llm.spent_in}/{llm.spent_out}")

    elif a.cmd == "fetch":
        from .sources import fetch_patient
        rec = fetch_patient(a.base, a.patient, a.token)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rec.to_bundle(), indent=1), encoding="utf-8")
        print(f"{len(rec.resources)} resources -> {a.out}")

    elif a.cmd == "mimic-scope":
        from .record import PatientRecord
        from .scope import scope_admission
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        n = skipped = 0
        for p in sorted(Path(a.src).glob("*.json")):
            s = scope_admission(PatientRecord.from_file(p))
            if s is None:
                skipped += 1; continue
            (out / f"{p.stem}_adm.json").write_text(json.dumps(s.to_bundle()), encoding="utf-8"); n += 1
        print(f"wrote {n} admission-scoped bundles to {out} ({skipped} patients had no admission)")

    elif a.cmd == "mimic-split":
        from .sources import split_mimic
        ps = split_mimic(a.src, a.out, a.max)
        print(f"wrote {len(ps)} patient bundles to {a.out}")

    elif a.cmd == "synthea-import":
        from .record import PatientRecord
        from .sources import load_synthea_dir
        from .synth import plant
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        n = 0
        for p in load_synthea_dir(a.src):
            shutil.copy(p, out / p.name); n += 1
            if a.plant:
                rec = PatientRecord.from_file(p)
                for i, trap in enumerate(["injection_omit_med", "injection_no_allergy", "missing_allergies"]):
                    v = plant(rec, trap, seed=i)
                    (out / f"{p.stem}__{trap}.json").write_text(json.dumps(v.to_bundle()), encoding="utf-8")
        print(f"imported {n} Synthea patients into {out}")

    elif a.cmd == "progress":
        import time
        from .llm import USAGE_LOG
        print(f"{'stage':40} {'done':>9}  status   precision(noverify->verify)  recall_w(verify_bf)")
        for d in sorted(Path(a.results).iterdir()):
            f = d / "summary.json"
            if not f.exists() or d.name.startswith("mock"):
                continue
            g = json.loads(f.read_text(encoding="utf-8"))
            sysm = g.get("systems", {})
            pn = sysm.get("llm_noverify", {}).get("precision"); pv = sysm.get("llm_verify", {}).get("precision")
            rb = sysm.get("llm_verify_bf", {}).get("recall_w")
            status = "PARTIAL" if g.get("stopped_early") else "done"
            print(f"{d.name:40} {g['n_patients']:>4}/{g.get('n_target', '?'):<4}  {status:7}  {pn} -> {pv}{'':14}{rb}")
        if USAGE_LOG.exists():
            import datetime as dt
            # Observed 2026-11-27: usage fits a daily bucket that resets at 00:00 UTC, not a rolling 24h window
            # (this project logged 306K tokens in 24h on one model with a 200K/day cap).
            now = dt.datetime.now(dt.timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            used: dict[str, int] = {}
            for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                if r["t"] >= day_start and r["status"] == 200:
                    used[r["model"]] = used.get(r["model"], 0) + (r["prompt_tokens"] or 0) + (r["completion_tokens"] or 0)
            reset_local = dt.datetime.fromtimestamp(day_start + 86400).strftime("%H:%M")
            print(f"\ntokens this project used since 00:00 UTC (cap 200K/model/day, shared with other projects on the "
                  f"key; next reset {reset_local} local):")
            for m, n in sorted(used.items()):
                print(f"  {m:28} {n:>8,}")

    elif a.cmd == "serve":
        import uvicorn
        print(f"open http://{a.host}:{a.port}/  (SMART standalone: http://{a.host}:{a.port}/launch.html?iss=https://launch.smarthealthit.org/v/r4/fhir)")
        uvicorn.run("fhirsum.app:app", host=a.host, port=a.port)


if __name__ == "__main__":
    main()
