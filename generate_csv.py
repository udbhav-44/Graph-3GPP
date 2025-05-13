import os
import json
import csv

INPUT_FOLDER = "Results"
OUTPUT_FOLDER = "./neo4j_csv_output"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Containers for deduplication
authors = set()
documents = set()
tech_entities = set()
working_groups = set()
meetings = set()
agendas = set()

authored_rels = set()
mentions_rels = set()
belongs_to_rels = set()
references_rels = set()
appears_in_rels = set()

def clean_list(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    return [val]

def safe_str(val):
    return "" if val is None else str(val)

def write_csv(filename, fieldnames, rows):
    with open(os.path.join(OUTPUT_FOLDER, filename), "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

# Process each JSON file
for root, dirs, files in os.walk(INPUT_FOLDER):
    for file in files:
        if not file.endswith(".json"):
            continue

        with open(os.path.join(root, file), "r", encoding="utf-8") as f:
            data = json.load(f)

        # Authors
        for a in data.get("authors", []):
            authors.add((a["name"], "|".join(clean_list(a.get("aliases", [])))))

        # Documents
        for d in data.get("documents", []):
            doc_id = d["doc_id"]
            tags = "|".join(clean_list(d.get("tags")))
            keywords = "|".join(clean_list(d.get("keywords")))
            agenda_ids = clean_list(d.get("agenda_id"))

            documents.add((
                doc_id,
                safe_str(d.get("version")),
                d["title"],
                d["release"],
                safe_str(d.get("type")),
                tags,
                d["summary"],
                d["topic"],
                keywords,
                d["meeting_id"],
                d["status"],
                safe_str(d.get("source_path"))
            ))

            # Reference relationships
            for rel in data.get("references", []):
                references_rels.add((
                    doc_id,
                    rel["cited_doc_id"],
                    safe_str(rel.get("type_of_reference")),
                    rel["details"]
                ))

            # Agenda-document relation
            for agenda_id in agenda_ids:
                appears_in_rels.add((
                    agenda_id,
                    doc_id,
                    ""  # page_range might be None, default to empty
                ))

        # Technology Entities
        for te in data.get("technology_entities", []):
            tech_entities.add((
                te["canonical_name"],
                "|".join(clean_list(te.get("aliases", []))),
                safe_str(te.get("description"))
            ))

        # Working Groups
        for wg in data.get("working_groups", []):
            working_groups.add((wg["id"], wg["name"], wg["description"]))

        # Meetings
        for m in data.get("meetings", []):
            meetings.add((m["meeting_id"], m["venue"], m["wg"], m["topic"]))

        # Agendas
        for a in data.get("agendas", []):
            agendas.add((
                a["agenda_id"],
                a.get("meeting_id", ""),
                a.get("topic", ""),
                a.get("description", "")
            ))

        # Authored
        for rel in data.get("authored", []):
            authored_rels.add((rel["contributor_name"], rel["doc_id"], rel["contribution_type"]))

        # Mentions
        for rel in data.get("mentions", []):
            mentions_rels.add((rel["doc_id"], rel["entity_name"], rel["context"], rel["frequency"]))

        # Belongs_to
        for rel in data.get("belongs_to", []):
            belongs_to_rels.add((rel["doc_id"], rel["wg_name"], rel["role_in_group"]))

        # Appears in
        for rel in data.get("appears_in", []):
            appears_in_rels.add((
                rel["agenda_id"],
                rel["doc_id"],
                safe_str(rel.get("page_range", ""))
            ))

# Write Node CSVs
write_csv("authors.csv", ["name", "aliases"], [
    {"name": a, "aliases": al} for a, al in authors
])

write_csv("documents.csv", [
    "doc_id", "version", "title", "release", "type", "tags", "summary", "topic", "keywords", "meeting_id", "status", "source_path"
], [
    {
        "doc_id": doc_id, "version": ver, "title": title, "release": rel,
        "type": typ, "tags": tags, "summary": summ, "topic": topic,
        "keywords": kw, "meeting_id": mid, "status": status, "source_path": link
    }
    for (doc_id, ver, title, rel, typ, tags, summ, topic, kw, mid, status, link) in documents
])

write_csv("technology_entities.csv", ["canonical_name", "aliases", "description"], [
    {"canonical_name": n, "aliases": al, "description": desc} for n, al, desc in tech_entities
])

write_csv("working_groups.csv", ["id", "name", "description"], [
    {"id": i, "name": n, "description": d} for i, n, d in working_groups
])

write_csv("meetings.csv", ["meeting_id", "venue", "wg", "topic"], [
    {"meeting_id": mid, "venue": v, "wg": wg, "topic": t} for mid, v, wg, t in meetings
])

write_csv("agendas.csv", ["agenda_id", "meeting_id", "topic", "description"], [
    {"agenda_id": aid, "meeting_id": mid, "topic": t, "description": d} for aid, mid, t, d in agendas
])

# Relationship CSVs
write_csv("authored.csv", ["contributor_name", "doc_id", "contribution_type"], [
    {"contributor_name": a, "doc_id": d, "contribution_type": c} for a, d, c in authored_rels
])

write_csv("mentions.csv", ["doc_id", "entity_name", "context", "frequency"], [
    {"doc_id": d, "entity_name": e, "context": ctx, "frequency": f} for d, e, ctx, f in mentions_rels
])

write_csv("belongs_to.csv", ["doc_id", "wg_name", "role_in_group"], [
    {"doc_id": d, "wg_name": w, "role_in_group": r} for d, w, r in belongs_to_rels
])

write_csv("references.csv", ["source_doc_id", "cited_doc_id", "type_of_reference", "details"], [
    {"source_doc_id": s, "cited_doc_id": c, "type_of_reference": t, "details": d}
    for s, c, t, d in references_rels
])

write_csv("appears_in.csv", ["agenda_id", "doc_id", "page_range"], [
    {"agenda_id": a, "doc_id": d, "page_range": p} for a, d, p in appears_in_rels
])

print("✅ All CSVs generated in:", OUTPUT_FOLDER)
