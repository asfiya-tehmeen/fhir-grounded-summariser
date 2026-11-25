"""FastAPI app: serves the SMART on FHIR launch page + viewer, and the summarise API.

SMART flow (browser side, fhirclient.js): launch.html -> authorize at the EHR/sandbox -> index.html ->
fetch the patient's resources with the access token -> POST them to /api/summarise_bundle.
Local mode: pick a bundle from data/ (generated / Synthea / MIMIC) and POST /api/summarise_file."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .llm import load_env, make_llm
from .record import PatientRecord
from .render import to_json
from .summarise import summarise, template_summary

load_env()
STATIC = Path(__file__).parent / "static"
DATA_DIRS = [Path(p) for p in os.environ.get("FHIRSUM_DATA_DIRS", "data/generated;data/synthea;data/mimic").split(";")]
app = FastAPI(title="FHIR-grounded summariser")
_llms: dict[str, object] = {}


def llm_for(provider: str):
    if provider not in _llms:
        _llms[provider] = make_llm(provider, os.environ.get(f"FHIRSUM_{provider.upper()}_MODEL") or None)
    return _llms[provider]


class FileReq(BaseModel):
    path: str
    summary_type: str = "handoff"
    provider: str = "groq"
    verify: bool = True


class BundleReq(BaseModel):
    resources: list[dict]
    summary_type: str = "handoff"
    provider: str = "groq"
    verify: bool = True


def _run(rec: PatientRecord, summary_type: str, provider: str, verify: bool) -> dict:
    if summary_type not in ("handoff", "medrec", "patient"):
        raise HTTPException(400, "summary_type must be handoff|medrec|patient")
    if provider == "template":
        return to_json(rec, template_summary(rec, summary_type))
    try:
        llm = llm_for(provider)
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return to_json(rec, summarise(rec, llm, summary_type, verify=verify))


@app.get("/api/patients")
def patients():
    out = []
    for d in DATA_DIRS:
        if d.exists():
            out += [{"path": str(p).replace("\\", "/"), "name": p.stem, "dir": d.name} for p in sorted(d.glob("*.json"))
                    if not p.name.startswith(("hospitalInformation", "practitionerInformation"))]
    return out


@app.post("/api/summarise_file")
def summarise_file(req: FileReq):
    p = Path(req.path).resolve()
    if not any(str(p).startswith(str(d.resolve())) for d in DATA_DIRS):
        raise HTTPException(403, "path outside data directories")
    return _run(PatientRecord.from_file(p), req.summary_type, req.provider, req.verify)


@app.post("/api/summarise_bundle")
def summarise_bundle(req: BundleReq):
    rec = PatientRecord.from_resources(req.resources, source="smart")
    if not rec.patient:
        raise HTTPException(400, "no Patient resource in payload")
    return _run(rec, req.summary_type, req.provider, req.verify)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
