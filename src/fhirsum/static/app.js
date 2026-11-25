// Viewer + SMART on FHIR client. If the page was opened by a SMART launch, the patient's resources are
// fetched in the browser with the access token and sent to the backend; otherwise local bundles are listed.
const $ = (id) => document.getElementById(id);
let smartResources = null;
let lastResources = {};

const TYPES = ["Condition", "MedicationRequest", "AllergyIntolerance", "Observation", "Encounter", "DocumentReference"];

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c])); }

async function initSmart() {
  const p = new URLSearchParams(location.search);
  const hasState = p.has("state") || Object.keys(sessionStorage).some(k => k === "SMART_KEY");
  if (!hasState || typeof FHIR === "undefined") return false;
  try {
    $("status").textContent = "SMART: fetching patient…";
    const client = await FHIR.oauth2.ready();
    const patient = await client.patient.read();
    const res = [patient];
    for (const t of TYPES) {
      try {
        const items = await client.request(`${t}?patient=${client.patient.id}&_count=200`, { pageLimit: 5, flat: true });
        res.push(...items.filter(r => r && r.resourceType === t));
      } catch (e) { console.warn("fetch failed", t, e); }
    }
    smartResources = res;
    $("patient").innerHTML = `<option value="smart">SMART launch: Patient/${esc(patient.id)} (${res.length} resources)</option>`;
    $("status").textContent = "";
    return true;
  } catch (e) {
    $("status").textContent = "SMART launch failed: " + e;
    return false;
  }
}

async function loadLocal() {
  const r = await fetch("/api/patients");
  const list = await r.json();
  $("patient").innerHTML = list.length
    ? list.map(p => `<option value="${esc(p.path)}">${esc(p.dir)} / ${esc(p.name)}</option>`).join("")
    : `<option value="">No local bundles. Run: fhirsum gen-suite</option>`;
}

function chip(ref) { return `<button class="chip" data-ref="${esc(ref)}" title="${esc(ref)}">${esc(ref.split("/")[0])}</button>`; }

function render(d) {
  lastResources = d.resources || {};
  let h = `<p class="disclaimer">${esc(d.disclaimer)}</p>`;
  h += `<p class="muted">Patient ${esc(d.patient.id)} · ${esc(d.patient.gender)} · age ${esc(d.patient.age)} · source ${esc(d.patient.source)} · mode <b>${esc(d.mode)}</b></p>`;
  if (d.checks.length) {
    h += `<div class="checks"><h2>System checks (code, not the model)</h2><ul>` +
      d.checks.map(c => `<li><b>${esc(c.kind)}</b>: ${esc(c.message)} ${c.refs.map(chip).join("")}</li>`).join("") + `</ul></div>`;
  }
  for (const s of d.sections) {
    h += `<h2>${esc(s.name)}</h2><ul>` + s.claims.map(c =>
      `<li>${esc(c.text)}${c.origin === "code" && d.mode !== "template" ? ' <span class="reason">(added by completeness check)</span>' : ""} ${c.resolved_refs.map(chip).join("")}${c.reasons && c.reasons.length ? ` <span class="reason">⚠ ${esc(c.reasons.join("; "))}</span>` : ""}</li>`).join("") + `</ul>`;
  }
  if (d.dropped.length) {
    h += `<details class="dropped"><summary>Removed by verifier (${d.dropped.length})</summary><ul>` +
      d.dropped.map(c => `<li><s>${esc(c.text)}</s><br><span class="reason">${esc(c.reasons.join("; "))}</span></li>`).join("") + `</ul></details>`;
  }
  const st = d.stats;
  h += `<p class="stats">kept ${st.kept} · dropped ${st.dropped} · malformed ${st.malformed} · ${st.latency_s}s · tokens ${st.tokens_in}/${st.tokens_out}</p>`;
  $("summary").innerHTML = h;
}

document.addEventListener("click", (e) => {
  const b = e.target.closest(".chip");
  if (!b) return;
  const ref = b.dataset.ref;
  $("json").textContent = ref + "\n\n" + JSON.stringify(lastResources[ref] || "(not included)", null, 2);
});

$("go").addEventListener("click", async () => {
  const body = { summary_type: $("stype").value, provider: $("provider").value, verify: $("verify").checked };
  let url;
  if ($("patient").value === "smart") { url = "/api/summarise_bundle"; body.resources = smartResources; }
  else { url = "/api/summarise_file"; body.path = $("patient").value; }
  if (!body.path && !body.resources) return;
  $("go").disabled = true; $("status").textContent = "Summarising…";
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.statusText);
    render(d); $("status").textContent = "";
  } catch (e) { $("status").textContent = "Error: " + e.message; }
  finally { $("go").disabled = false; }
});

(async () => { if (!(await initSmart())) await loadLocal(); })();
