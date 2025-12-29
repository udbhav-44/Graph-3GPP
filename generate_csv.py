"""
JSON to CSV Converter for Neo4j Import

This script traverses a directory of JSON files containing 3GPP meeting data and converts them into
normalized CSV files suitable for bulk import into a Neo4j graph database. It handles the extraction,
deduplication, and formatting of various nodes and relationships.

Key Features:
- Recursively reads JSON files from a specified input directory.
- Extracts and dedupes entities: Authors, Documents, Technology Entities, Working Groups, Meetings, Agendas.
- Extracts and aggregates relationships: Authored, Mentions, Belongs To, References, Appears In.
- Handles missing data gracefully with safe string conversion.
- Outputs separate CSV files for each node and relationship type.
- Ensures correct character encoding (UTF-8).

Input:
- Directory containing processed JSON files (default: "Results")

Output:
- Directory containing generated CSV files (default: "./neo4j_csv_output2")
  - authors.csv
  - documents.csv
  - technology_entities.csv
  - working_groups.csv
  - meetings.csv
  - agendas.csv
  - authored.csv
  - mentions.csv
  - belongs_to.csv
  - references.csv
  - appears_in.csv
"""

import os
import json
import csv

INPUT_FOLDER = "Results"
OUTPUT_FOLDER = "./neo4j_csv_output2"
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
            release = d.get("release")

            documents.add((
                doc_id,
                safe_str(d.get("version")),
                d["title"],
                release,
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
                    rel.get("details", "")
                ))

            # Agenda-document relation (includes release)
            for agenda_id in agenda_ids:
                appears_in_rels.add((
                    agenda_id,
                    release,
                    doc_id,
                    ""  # page_range might be None
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
            meetings.add((m["meeting_id"], m.get("venue", ""), m.get("wg", ""), m.get("topic", "")))

        # Agendas (store release)
        for a in data.get("agendas", []):
            # If release not in agenda, try to get from linked document
            agenda_release = a.get("release")
            if not agenda_release:
                for d in data.get("documents", []):
                    if a["agenda_id"] in clean_list(d.get("agenda_id")):
                        agenda_release = d.get("release")
                        break
            agendas.add((
                a["agenda_id"],
                agenda_release if agenda_release else "",
                a.get("topic", ""),
                a.get("description", "")
            ))

        # Authored
        for rel in data.get("authored", []):
            authored_rels.add((rel["contributor_name"], rel["doc_id"], rel.get("contribution_type", "")))

        # Mentions
        for rel in data.get("mentions", []):
            mentions_rels.add((rel["doc_id"], rel["entity_name"], rel.get("context", ""), rel.get("frequency", "")))

        # Belongs_to
        for rel in data.get("belongs_to", []):
            belongs_to_rels.add((rel["doc_id"], rel.get("wg_name", ""), rel.get("role_in_group", "")))

        # Appears in (already handled above)

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

write_csv("agendas.csv", ["agenda_id", "release", "topic", "description"], [
    {"agenda_id": aid, "release": rel, "topic": t, "description": d} for aid, rel, t, d in agendas
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

write_csv("appears_in.csv", ["agenda_id", "release", "doc_id", "page_range"], [
    {"agenda_id": a, "release": r, "doc_id": d, "page_range": p} for a, r, d, p in appears_in_rels
])

print("All CSVs generated in:", OUTPUT_FOLDER)
