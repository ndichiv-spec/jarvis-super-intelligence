"""Builder for sector-map.json (concise sector -> classification -> location map).

This reconciles the §2 'sector inventory' filename with the naming note in the
audit brief: it is a DERIVED artifact that re-surfaces the sectors from
platform-inventory.json together with their §3 classification + evidence
cross-references from sector-state-classification.json. No new claims; both
source JSONs are already json.tool-validated.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "sector-map.json")

with open(os.path.join(HERE, "..", "platform-inventory.json"), encoding="utf-8") as f:
    inv = json.load(f)
with open(os.path.join(HERE, "..", "sector-state-classification.json"), encoding="utf-8") as f:
    cls = json.load(f)

# Index classification components by a normalized key = lowercased component name
# so we can cross-link each inventory sector to its §3 evidence entries.
by_component = {}
for c in cls["components"]:
    by_component[c["component"].lower()] = c

rows = []
for s in inv["sectors"]:
    key = s["sector"].lower()
    evidence_refs = []
    if key in by_component:
        c = by_component[key]
        evidence_refs = {
            "classification": c["classification"],
            "evidence_count": len(c["evidence"]),
            "component": c["component"],
        }
    rows.append({
        "sector": s["sector"],
        "classification": s["classification"],
        "evidence_crossref": evidence_refs if evidence_refs else None,
        "backend_location": s.get("backend_location"),
        "frontend_location": s.get("frontend_location"),
        "apis": s.get("apis"),
        "database_store": s.get("database_store"),
        "current_execution_path": s.get("current_execution_path"),
    })

doc = {
    "artifact": "sector-map",
    "generated_by": "JARVIS Platform X-Ray - derived §2/§3 sector map",
    "purpose": "Reconciles the 'sector-map.json' filename with platform-inventory.json (§2 inventory) + sector-state-classification.json (§3). A sector is listed by classification, location, API surface and live execution path, with a cross-ref to its §3 evidence entries.",
    "source_of_truth": {
        "inventory": "platform-inventory.json (sectors[])",
        "classification": "sector-state-classification.json (components[])",
    },
    "note_on_line_numbers": "All file:line citations live in the source JSONs and are true disk line numbers (rg -n / py_compile), NOT the editor ruler.",
    "sectors": rows,
    "summary": {
        "total_sectors": len(rows),
        "sectors_with_direct_classification_crossref": sum(1 for r in rows if r["evidence_crossref"]),
        "classification_legend": cls["tag_legend"],
    },
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("WROTE", OUT, os.path.getsize(OUT), "bytes; sectors:", len(rows))
