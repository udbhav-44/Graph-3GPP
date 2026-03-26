"""
JSON to CSV Converter for Neo4j Import
=======================================

Traverses a directory of LLM-extracted JSON files and writes 11 CSV files
suitable for bulk import into Neo4j via LOAD CSV.

Bugs fixed vs. original version
--------------------------------
1. Agenda nodes now carry meeting_id (was silently dropped from the Pydantic
   model's meeting_id field before writing). Agendas are now keyed by
   (agenda_id, meeting_id) — agenda item "9" at RAN1#116 and "9" at RAN1#118
   are different nodes.
2. Agenda topics/descriptions are aggregated as semicolon-separated unique
   values across all documents that reference that agenda item at that meeting,
   instead of storing one LLM-generated blob per duplicate node.
3. Agenda CSV columns renamed: topic → topics, description → descriptions
   (these are the actual property names on live Neo4j nodes and must match
   what the LOAD CSV script and full-text index use).
4. appears_in.csv now includes a meeting_id column so the LOAD CSV can MERGE
   Agenda nodes on the composite key (agenda_id, meeting_id).
5. References loop moved outside the per-document loop — previously every
   reference in a file was attributed to every document in that file
   (N-duplication bug). Now attributed once to the first document.
6. WorkingGroup deduplication keyed on (id, name), not (id, name, description).
   Prevents ~1,400 near-duplicate WorkingGroup rows per meeting.

Input:   Results/  (recursive walk for *.json)
Output:  ./neo4j_csv_output2/
"""

import os
import json
import csv
from collections import defaultdict

INPUT_FOLDER = "Results"
OUTPUT_FOLDER = "./neo4j_csv_output2"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ── Node containers ──────────────────────────────────────────────────────────
authors      = set()   # (name, aliases_pipe)
documents    = set()   # (doc_id, version, title, release, type, tags, summary,
                       #  topic, keywords, meeting_id, status, source_path)
tech_entities = set()  # (canonical_name, aliases_pipe, description)
meetings     = set()   # (meeting_id, venue, wg, topic)

# WorkingGroup: key=(id, name) → description  (first-seen wins)
wg_dict: dict = {}

# Agenda: key=(agenda_id, meeting_id) → {'topics': set, 'descriptions': set, 'release': str}
agenda_dict: dict = defaultdict(lambda: {"topics": set(), "descriptions": set(), "release": ""})

# ── Relationship containers ───────────────────────────────────────────────────
authored_rels    = set()  # (contributor_name, doc_id, contribution_type)
mentions_rels    = set()  # (doc_id, entity_name, context, frequency)
belongs_to_rels  = set()  # (doc_id, wg_name, role_in_group)
references_rels  = set()  # (source_doc_id, cited_doc_id, type_of_reference, details)
# appears_in now includes meeting_id for proper Agenda MERGE in LOAD CSV
appears_in_rels  = set()  # (agenda_id, meeting_id, release, doc_id, page_range)


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_list(val):
    if not val:
        return []
    if isinstance(val, list):
        return [v for v in val if v is not None]
    return [val]

def safe_str(val):
    return "" if val is None else str(val)

def write_csv(filename, fieldnames, rows):
    path = os.path.join(OUTPUT_FOLDER, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ── Main processing loop ──────────────────────────────────────────────────────

for root, dirs, files in os.walk(INPUT_FOLDER):
    for file in files:
        if not file.endswith(".json"):
            continue

        filepath = os.path.join(root, file)
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"  SKIP (invalid JSON): {filepath} — {e}")
                continue

        # ── Authors ──────────────────────────────────────────────────────────
        for a in data.get("authors", []):
            if not a.get("name"):
                continue
            authors.add((a["name"], "|".join(clean_list(a.get("aliases", [])))))

        # ── Build a page_range lookup from the LLM's appears_in list ─────────
        # appears_in entries: {agenda_id, doc_id, page_range}
        page_range_lookup: dict = {}
        for ai in data.get("appears_in", []):
            key = (safe_str(ai.get("agenda_id")), safe_str(ai.get("doc_id")))
            page_range_lookup[key] = safe_str(ai.get("page_range", ""))

        # ── Documents (and their direct relationships) ────────────────────────
        doc_ids_in_file = []

        for d in data.get("documents", []):
            doc_id = d.get("doc_id")
            if not doc_id:
                continue

            doc_ids_in_file.append(doc_id)
            tags     = "|".join(clean_list(d.get("tags")))
            keywords = "|".join(clean_list(d.get("keywords")))
            agenda_ids   = clean_list(d.get("agenda_id"))
            release      = safe_str(d.get("release"))
            meeting_id   = safe_str(d.get("meeting_id"))
            topic        = safe_str(d.get("topic"))

            documents.add((
                doc_id,
                safe_str(d.get("version")),
                safe_str(d.get("title")),
                release,
                safe_str(d.get("type")),
                tags,
                safe_str(d.get("summary")),
                topic,
                keywords,
                meeting_id,
                safe_str(d.get("status")),
                safe_str(d.get("source_path")),
            ))

            # APPEARS_IN: Document → Agenda
            # Use document.agenda_id as the source of truth; look up page_range
            # from the LLM's appears_in list if available.
            for agenda_id in agenda_ids:
                if not agenda_id:
                    continue
                page_range = page_range_lookup.get((safe_str(agenda_id), doc_id), "")
                appears_in_rels.add((
                    safe_str(agenda_id),
                    meeting_id,
                    release,
                    doc_id,
                    page_range,
                ))

                # Accumulate topic text onto the Agenda node
                key = (safe_str(agenda_id), meeting_id)
                if topic:
                    agenda_dict[key]["topics"].add(topic)
                if not agenda_dict[key]["release"] and release:
                    agenda_dict[key]["release"] = release

        # ── References ────────────────────────────────────────────────────────
        # Bug fix: attribute references to the FIRST document in the file, not
        # to every document (old code nested this loop inside the doc loop,
        # creating N copies of every reference for N documents in the file).
        # Limitation: source_doc_id is not extracted by the LLM so we infer it.
        references_list = data.get("references", [])
        if references_list and doc_ids_in_file:
            source_doc_id = doc_ids_in_file[0]
            for rel in references_list:
                cited = safe_str(rel.get("cited_doc_id", ""))
                if not cited or cited == source_doc_id:
                    continue  # skip empty or self-reference
                references_rels.add((
                    source_doc_id,
                    cited,
                    safe_str(rel.get("type_of_reference")),
                    safe_str(rel.get("details", "")),
                ))

        # ── Technology Entities ───────────────────────────────────────────────
        for te in data.get("technology_entities", []):
            if not te.get("canonical_name"):
                continue
            tech_entities.add((
                te["canonical_name"],
                "|".join(clean_list(te.get("aliases", []))),
                safe_str(te.get("description")),
            ))

        # ── Working Groups (deduplicate by id+name, keep first description) ──
        for wg in data.get("working_groups", []):
            wg_id   = safe_str(wg.get("id"))
            wg_name = safe_str(wg.get("name"))
            if not wg_id:
                continue
            key = (wg_id, wg_name)
            if key not in wg_dict:
                wg_dict[key] = safe_str(wg.get("description", ""))

        # ── Meetings ─────────────────────────────────────────────────────────
        for m in data.get("meetings", []):
            mid = safe_str(m.get("meeting_id", ""))
            if not mid:
                continue
            meetings.add((mid, safe_str(m.get("venue", "")), safe_str(m.get("wg", "")), safe_str(m.get("topic", ""))))

        # ── Agendas from the LLM's agendas list ──────────────────────────────
        # Supplement the topic/description aggregation with the LLM's explicit
        # agenda entries.  meeting_id is inferred from linked documents when
        # the LLM doesn't fill it in.
        for a in data.get("agendas", []):
            agenda_id = safe_str(a.get("agenda_id", ""))
            if not agenda_id:
                continue

            # Resolve meeting_id: use field if present, else infer from docs
            mid = safe_str(a.get("meeting_id", ""))
            if not mid:
                for d in data.get("documents", []):
                    if agenda_id in [safe_str(x) for x in clean_list(d.get("agenda_id"))]:
                        mid = safe_str(d.get("meeting_id", ""))
                        break

            key = (agenda_id, mid)
            t = safe_str(a.get("topic", ""))
            desc = safe_str(a.get("description", ""))
            if t:
                agenda_dict[key]["topics"].add(t)
            if desc:
                agenda_dict[key]["descriptions"].add(desc)
            rel = safe_str(a.get("release", ""))
            if rel and not agenda_dict[key]["release"]:
                agenda_dict[key]["release"] = rel

        # ── Authored ─────────────────────────────────────────────────────────
        for rel in data.get("authored", []):
            name = safe_str(rel.get("contributor_name", ""))
            did  = safe_str(rel.get("doc_id", ""))
            if not name or not did:
                continue
            authored_rels.add((name, did, safe_str(rel.get("contribution_type", ""))))

        # ── Mentions ─────────────────────────────────────────────────────────
        for rel in data.get("mentions", []):
            did    = safe_str(rel.get("doc_id", ""))
            entity = safe_str(rel.get("entity_name", ""))
            if not did or not entity:
                continue
            mentions_rels.add((did, entity, safe_str(rel.get("context", "")), safe_str(rel.get("frequency", ""))))

        # ── Belongs_to ───────────────────────────────────────────────────────
        for rel in data.get("belongs_to", []):
            did = safe_str(rel.get("doc_id", ""))
            wg  = safe_str(rel.get("wg_name", ""))
            if not did or not wg:
                continue
            belongs_to_rels.add((did, wg, safe_str(rel.get("role_in_group", ""))))


# ── Write Node CSVs ───────────────────────────────────────────────────────────

write_csv("authors.csv", ["name", "aliases"], [
    {"name": name, "aliases": aliases}
    for name, aliases in authors
])

write_csv("documents.csv", [
    "doc_id", "version", "title", "release", "type", "tags",
    "summary", "topic", "keywords", "meeting_id", "status", "source_path",
], [
    {
        "doc_id": doc_id, "version": ver, "title": title, "release": rel,
        "type": typ, "tags": tags, "summary": summ, "topic": topic,
        "keywords": kw, "meeting_id": mid, "status": status, "source_path": link,
    }
    for doc_id, ver, title, rel, typ, tags, summ, topic, kw, mid, status, link in documents
])

write_csv("technology_entities.csv", ["canonical_name", "aliases", "description"], [
    {"canonical_name": name, "aliases": aliases, "description": desc}
    for name, aliases, desc in tech_entities
])

write_csv("working_groups.csv", ["id", "name", "description"], [
    {"id": wg_id, "name": wg_name, "description": desc}
    for (wg_id, wg_name), desc in wg_dict.items()
])

write_csv("meetings.csv", ["meeting_id", "venue", "wg", "topic"], [
    {"meeting_id": mid, "venue": v, "wg": wg, "topic": t}
    for mid, v, wg, t in meetings
])

# Agendas: one row per (agenda_id, meeting_id).
# topics and descriptions are semicolon-separated unique values aggregated from
# all documents that reference this agenda item at this meeting.
# Column names are topics/descriptions (plural) to match live Neo4j properties
# and the full-text index definition.
write_csv("agendas.csv", ["agenda_id", "meeting_id", "release", "topics", "descriptions"], [
    {
        "agenda_id":    agenda_id,
        "meeting_id":   meeting_id,
        "release":      info["release"],
        "topics":       "; ".join(sorted(info["topics"])),
        "descriptions": "; ".join(sorted(info["descriptions"])),
    }
    for (agenda_id, meeting_id), info in sorted(agenda_dict.items())
])


# ── Write Relationship CSVs ───────────────────────────────────────────────────

write_csv("authored.csv", ["contributor_name", "doc_id", "contribution_type"], [
    {"contributor_name": name, "doc_id": did, "contribution_type": ctype}
    for name, did, ctype in authored_rels
])

write_csv("mentions.csv", ["doc_id", "entity_name", "context", "frequency"], [
    {"doc_id": did, "entity_name": entity, "context": ctx, "frequency": freq}
    for did, entity, ctx, freq in mentions_rels
])

write_csv("belongs_to.csv", ["doc_id", "wg_name", "role_in_group"], [
    {"doc_id": did, "wg_name": wg, "role_in_group": role}
    for did, wg, role in belongs_to_rels
])

write_csv("references.csv", ["source_doc_id", "cited_doc_id", "type_of_reference", "details"], [
    {"source_doc_id": src, "cited_doc_id": cited, "type_of_reference": rtype, "details": details}
    for src, cited, rtype, details in references_rels
])

# appears_in now includes meeting_id so LOAD CSV can MERGE Agenda on
# the composite key (agenda_id, meeting_id).
write_csv("appears_in.csv", ["agenda_id", "meeting_id", "release", "doc_id", "page_range"], [
    {"agenda_id": aid, "meeting_id": mid, "release": rel, "doc_id": did, "page_range": pr}
    for aid, mid, rel, did, pr in appears_in_rels
])

print(f"CSVs written to: {OUTPUT_FOLDER}")
print(f"  documents:          {len(documents)}")
print(f"  authors:            {len(authors)}")
print(f"  technology_entities:{len(tech_entities)}")
print(f"  working_groups:     {len(wg_dict)}")
print(f"  meetings:           {len(meetings)}")
print(f"  agendas:            {len(agenda_dict)}  (unique agenda_id+meeting_id pairs)")
print(f"  authored rels:      {len(authored_rels)}")
print(f"  mentions rels:      {len(mentions_rels)}")
print(f"  belongs_to rels:    {len(belongs_to_rels)}")
print(f"  references rels:    {len(references_rels)}")
print(f"  appears_in rels:    {len(appears_in_rels)}")
