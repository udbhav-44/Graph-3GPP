# Graph-3GPP

A pipeline that builds a Neo4j knowledge graph from 3GPP RAN WG1 meeting documents. Feeds the **Chat3GPP** RAG search system.

---

## What This Does

```
ZIP archives (3GPP FTP)
    └─▶  Process_3GPP_Docs.py   extract text, call DeepSeek LLM, write JSON
            └─▶  generate_csv.py     aggregate JSONs → 11 CSV files
                    └─▶  LOAD CSV         bulk import into Neo4j
                              └─▶  Chat3GPP search uses the graph
```

Meetings covered: **RAN1 #116, #116b, #117, #118, #118b, #119** (~10,700 documents).

---

## Repository Structure

```
Graph-3GPP/
├── DataModel/
│   └── datamodel.py          Pydantic v1 schema — defines every node and edge the LLM extracts
├── Process_3GPP_Docs.py      Step 1: ZIP → Word doc → LLM → JSON
├── generate_csv.py           Step 2: JSON directory → 11 CSVs for Neo4j
├── query_graph.py            CLI search: Cypher full-text search → download docs → RAG
├── beta_testing/
│   ├── app.py                Gradio UI (port 7860) used during beta testing period
│   └── feedback_log.csv      24 beta feedback entries
├── neo4j_csv_output2/        Output CSVs (gitignored if large; regenerate with generate_csv.py)
├── requirements.txt          Full pip-freeze of the dev environment
└── .env                      API keys (never commit)
```

---

## Prerequisites

- Python 3.10+
- Neo4j 5.x with the **APOC plugin** (required for post-import cleanup)
- DeepSeek API key (`deepseek-reasoner` + `deepseek-chat`)
- LibreOffice installed (for `.doc` → `.docx` conversion during document processing)

---

## Setup

```bash
git clone git@github.com:udbhav-44/Graph-3GPP.git
cd Graph-3GPP
pip install -r requirements.txt
cp .env.example .env   # add DEEPSEEK_API_KEY
```

---

## Step 1 — Process Documents (`Process_3GPP_Docs.py`)

Reads a directory of ZIP archives. Each ZIP contains one or more `.doc`/`.docx` 3GPP contribution files. For each document:

1. Extracts text via `UnstructuredWordDocumentLoader`
2. Calls `deepseek-reasoner` with a structured output prompt to extract a `DataModel` JSON
3. Falls back to raw completion + regex JSON extraction on failure
4. Falls back to `deepseek-chat` for JSON repair on parse failure
5. Writes `<docname>.json` to the output directory

**Configure before running** — edit the `main()` function:

```python
directory_path  = Path("/path/to/DATA/tsg_ran/WG1_RL1/TSGR1_119/Docs")
output_directory = Path("/path/to/Results/TSG_119/Docs")
```

Run once per meeting directory:

```bash
python Process_3GPP_Docs.py
```

Processed files are tracked in `processed_files.json` so re-runs skip already-done ZIPs.

**Token limit**: Documents over 65,000 tokens (tiktoken `cl100k_base`) are skipped. This affects very large session-note documents.

---

## Step 2 — Generate CSVs (`generate_csv.py`)

Walks the `Results/` directory recursively and aggregates all JSON files into 11 CSVs.

```bash
python generate_csv.py
```

Output goes to `./neo4j_csv_output2/`. The script prints row counts on completion.

### What each CSV contains

| File | Node/Rel | Key | Notes |
|---|---|---|---|
| `documents.csv` | `Document` | `doc_id` | Core document metadata |
| `authors.csv` | `Contributor` | `name` | Pipe-delimited `aliases` |
| `technology_entities.csv` | `TechnologyEntity` | `canonical_name` | Pipe-delimited `aliases` |
| `working_groups.csv` | `WorkingGroup` | `id` | Deduplicated by (id, name) |
| `meetings.csv` | `Meeting` | `meeting_id` | Venue, WG, topic |
| `agendas.csv` | `Agenda` | `(agenda_id, meeting_id)` | See note below |
| `authored.csv` | `AUTHORED` | — | Contributor → Document |
| `mentions.csv` | `MENTIONS` | — | Document → TechnologyEntity |
| `belongs_to.csv` | `BELONGS_TO` | — | Document → WorkingGroup |
| `references.csv` | `REFERENCES` | — | Document → Document |
| `appears_in.csv` | `APPEARS_IN` | — | Document → Agenda |

### Agenda node uniqueness — important

Agenda ID numbers like `"9"`, `"8.1"`, `"9.1.1"` repeat at every 3GPP meeting but refer to completely different agenda items. The uniqueness key is **(agenda_id, meeting_id)** — not just `agenda_id`. Each `agendas.csv` row has both columns and the LOAD CSV script MERGEs on both.

The `topics` and `descriptions` columns on Agenda nodes are semicolon-separated strings, aggregated from all documents that reference that agenda item at that meeting. This gives the full-text index rich content to match against.

---

## Step 3 — Neo4j Import

### Run Neo4j with APOC

```bash
docker run --name neo4j \
  --memory=64g --memory-swap=96g --cpus="24" \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  -e NEO4J_PLUGINS='["apoc"]' \
  -e NEO4J_apoc_export_file_enabled=true \
  -e NEO4J_apoc_import_file_enabled=true \
  -e NEO4J_dbms_security_procedures_unrestricted="apoc.*" \
  -v $PWD/neo4j_csv_output2:/var/lib/neo4j/import \
  -v neo4j_data:/data \
  neo4j:5
```

### LOAD CSV — run in order in Neo4j Browser or cypher-shell

**1. Constraints (run first — required for MERGE performance)**

```cypher
CREATE CONSTRAINT doc_unique       IF NOT EXISTS FOR (d:Document)         REQUIRE d.doc_id IS UNIQUE;
CREATE CONSTRAINT contrib_unique   IF NOT EXISTS FOR (c:Contributor)       REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT tech_unique      IF NOT EXISTS FOR (t:TechnologyEntity)  REQUIRE t.canonical_name IS UNIQUE;
CREATE CONSTRAINT meeting_unique   IF NOT EXISTS FOR (m:Meeting)           REQUIRE m.meeting_id IS UNIQUE;
CREATE CONSTRAINT wg_unique        IF NOT EXISTS FOR (w:WorkingGroup)      REQUIRE w.id IS UNIQUE;
CREATE CONSTRAINT agenda_unique    IF NOT EXISTS FOR (a:Agenda)            REQUIRE (a.agenda_id, a.meeting_id) IS NODE KEY;
```

**2. Nodes**

```cypher
// Documents
LOAD CSV WITH HEADERS FROM 'file:///documents.csv' AS row
MERGE (d:Document {doc_id: row.doc_id})
SET d.version    = row.version,
    d.title      = row.title,
    d.release    = row.release,
    d.type       = row.type,
    d.tags       = split(row.tags, '|'),
    d.summary    = row.summary,
    d.topic      = row.topic,
    d.keywords   = split(row.keywords, '|'),
    d.meeting_id = row.meeting_id,
    d.status     = row.status,
    d.source_path = row.source_path;

// Contributors
LOAD CSV WITH HEADERS FROM 'file:///authors.csv' AS row
MERGE (c:Contributor {name: row.name})
SET c.aliases = split(row.aliases, '|');

// TechnologyEntities
LOAD CSV WITH HEADERS FROM 'file:///technology_entities.csv' AS row
MERGE (t:TechnologyEntity {canonical_name: row.canonical_name})
SET t.aliases     = split(row.aliases, '|'),
    t.description = row.description;

// WorkingGroups
LOAD CSV WITH HEADERS FROM 'file:///working_groups.csv' AS row
MERGE (w:WorkingGroup {id: row.id})
SET w.name = row.name, w.description = row.description;

// Meetings
LOAD CSV WITH HEADERS FROM 'file:///meetings.csv' AS row
MERGE (m:Meeting {meeting_id: row.meeting_id})
SET m.venue = row.venue, m.wg = row.wg, m.topic = row.topic;

// Agendas — composite key: (agenda_id, meeting_id)
LOAD CSV WITH HEADERS FROM 'file:///agendas.csv' AS row
MERGE (a:Agenda {agenda_id: row.agenda_id, meeting_id: row.meeting_id})
SET a.release      = row.release,
    a.topics       = row.topics,
    a.descriptions = row.descriptions;
```

**3. Relationships**

```cypher
// AUTHORED: (Contributor)-[:AUTHORED]->(Document)
LOAD CSV WITH HEADERS FROM 'file:///authored.csv' AS row
MATCH (c:Contributor {name: row.contributor_name})
MATCH (d:Document    {doc_id: row.doc_id})
MERGE (c)-[:AUTHORED {contribution_type: row.contribution_type}]->(d);

// MENTIONS: (Document)-[:MENTIONS]->(TechnologyEntity)
LOAD CSV WITH HEADERS FROM 'file:///mentions.csv' AS row
MATCH (d:Document        {doc_id: row.doc_id})
MATCH (t:TechnologyEntity {canonical_name: row.entity_name})
MERGE (d)-[:MENTIONS {context: row.context, frequency: toIntegerOrNull(row.frequency)}]->(t);

// BELONGS_TO: (Document)-[:BELONGS_TO]->(WorkingGroup)
LOAD CSV WITH HEADERS FROM 'file:///belongs_to.csv' AS row
MATCH (d:Document     {doc_id: row.doc_id})
MATCH (w:WorkingGroup {id: row.wg_name})
MERGE (d)-[:BELONGS_TO {role_in_group: row.role_in_group}]->(w);

// APPEARS_IN: (Document)-[:APPEARS_IN]->(Agenda)
// Agenda is matched on the composite key (agenda_id, meeting_id).
LOAD CSV WITH HEADERS FROM 'file:///appears_in.csv' AS row
MATCH (d:Document {doc_id: row.doc_id})
MATCH (a:Agenda   {agenda_id: row.agenda_id, meeting_id: row.meeting_id})
MERGE (d)-[:APPEARS_IN {release: row.release, page_range: row.page_range}]->(a);

// REFERENCES: (Document)-[:REFERENCES]->(Document)
// Self-references are excluded.
LOAD CSV WITH HEADERS FROM 'file:///references.csv' AS row
MATCH (d1:Document {doc_id: row.source_doc_id})
MATCH (d2:Document {doc_id: row.cited_doc_id})
WHERE d1 <> d2
MERGE (d1)-[:REFERENCES {type_of_reference: row.type_of_reference, details: row.details}]->(d2);
```

**4. Full-text indexes** (required by the Chat3GPP search query)

```cypher
CREATE FULLTEXT INDEX docIndex       FOR (n:Document)         ON EACH [n.title, n.summary, n.keywords, n.topic, n.tags];
CREATE FULLTEXT INDEX agendaIndex    FOR (n:Agenda)           ON EACH [n.topics, n.descriptions, n.release];
CREATE FULLTEXT INDEX techEntityIndex FOR (n:TechnologyEntity) ON EACH [n.canonical_name, n.aliases, n.description];
```

**5. Post-import cleanup** (run after every import to remove pipeline artifacts)

```cypher
// Remove self-referencing REFERENCES edges
MATCH (d:Document)-[r:REFERENCES]->(d) DELETE r;

// Remove duplicate MENTIONS between the same doc-entity pair
MATCH (d:Document)-[r:MENTIONS]->(t:TechnologyEntity)
WITH d, t, collect(r) AS rels WHERE size(rels) > 1
FOREACH(i IN range(1, size(rels)-1) | DELETE rels[i]);

// Remove duplicate AUTHORED
MATCH (c:Contributor)-[r:AUTHORED]->(d:Document)
WITH c, d, collect(r) AS rels WHERE size(rels) > 1
FOREACH(i IN range(1, size(rels)-1) | DELETE rels[i]);

// Remove duplicate REFERENCES
MATCH (d1:Document)-[r:REFERENCES]->(d2:Document)
WHERE elementId(d1) <> elementId(d2)
WITH d1, d2, collect(r) AS rels WHERE size(rels) > 1
FOREACH(i IN range(1, size(rels)-1) | DELETE rels[i]);

// Remove orphan TechnologyEntity nodes (no MENTIONS — unlinked due to name mismatch)
MATCH (t:TechnologyEntity) WHERE NOT ()-[:MENTIONS]->(t) DELETE t;

// Remove orphan Contributors
MATCH (c:Contributor) WHERE NOT (c)-[:AUTHORED]->() DELETE c;

// Remove orphan Documents
MATCH (d:Document) WHERE NOT (d)--() DELETE d;
```

---

## Data Model

### Nodes

| Label | Key | Properties |
|---|---|---|
| `Document` | `doc_id` | `version`, `title`, `release`, `type`, `tags[]`, `summary`, `topic`, `keywords[]`, `meeting_id`, `status`, `source_path` |
| `Contributor` | `name` | `aliases[]` |
| `TechnologyEntity` | `canonical_name` | `aliases[]`, `description` |
| `WorkingGroup` | `id` | `name`, `description` |
| `Meeting` | `meeting_id` | `venue`, `wg`, `topic` |
| `Agenda` | `(agenda_id, meeting_id)` | `release`, `topics`, `descriptions` |

### Relationships

```
(Contributor)  -[:AUTHORED   {contribution_type}]->  (Document)
(Document)     -[:MENTIONS   {context, frequency}]->  (TechnologyEntity)
(Document)     -[:BELONGS_TO {role_in_group}]->        (WorkingGroup)
(Document)     -[:APPEARS_IN {release, page_range}]->  (Agenda)
(Document)     -[:REFERENCES {type_of_reference, details}]-> (Document)
```

### Full-text indexes

| Index name | Node label | Indexed properties |
|---|---|---|
| `docIndex` | `Document` | `title`, `summary`, `keywords`, `topic`, `tags` |
| `agendaIndex` | `Agenda` | `topics`, `descriptions`, `release` |
| `techEntityIndex` | `TechnologyEntity` | `canonical_name`, `aliases`, `description` |

**Critical**: the Agenda index covers `topics` and `descriptions` (plural). These match the property names on live Agenda nodes. An index built on `topic`/`description` (singular, from earlier CSV column names) will silently index nothing and return no results.

---

## How the Search Query Works (Chat3GPP)

The `search_and_generate` tool in `pipeline/Agents/LATS/OldfinTools.py` runs a three-branch Cypher query:

```
Branch A: docIndex full-text search on Document nodes
          → direct document matches, scored by BM25
Branch B: agendaIndex full-text search on Agenda nodes
          → Documents found via (Document)-[:APPEARS_IN]->(Agenda)
          → score boosted 2.3× if doc already found in Branch A
Branch C: techEntityIndex full-text search on TechnologyEntity nodes
          → Documents found via (Document)-[:MENTIONS]->(TechnologyEntity)
          → score weighted 0.7×
```

All three branches produce `{doc_id, score}` pairs. Scores are summed per `doc_id`. Documents with "Feature Lead Summary" in the title get a 2× boost. Top 15 returned.

---

## Known Limitations

### LLM extraction quality
- `release` and `type` fields have 100+ un-normalized variants (e.g., "Rel-19" / "Release 19" / "R19"). No normalization is applied during CSV generation. This affects filtering but not full-text search.
- `TechnologyEntity.canonical_name` and the `entity_name` in `MENTIONS` are extracted independently by the LLM. They often differ (full name vs. abbreviation), so many MENTIONS edges fail to link to existing TechnologyEntity nodes. Post-import cleanup removes the resulting orphan TechnologyEntity nodes.
- The `source_doc_id` in `REFERENCES` is inferred (the LLM doesn't extract it), so reference attribution is imperfect for ZIP files containing multiple documents.

### What was fixed in generate_csv.py (2025-03)
See the module docstring at the top of `generate_csv.py` for a full list. The main fix: Agenda nodes now carry `meeting_id`, enabling correct deduplication and meeting-scoped search.

---

## Environment Variables

```ini
# .env
DEEPSEEK_API_KEY=your_key_here
```

The Neo4j connection in `query_graph.py` and `beta_testing/app.py` is hardcoded. Update these before running:

```python
uri   = "bolt://localhost:7687"
uname = "neo4j"
pswd  = "your_password"
```

---

## Neo4j Backup & Restore

```bash
# Dump (Neo4j must be stopped)
neo4j-admin database dump neo4j --to-path ./neo4j-backups/

# Restore
neo4j-admin database load neo4j --from-path ./neo4j-backups/ --overwrite-destination
```
