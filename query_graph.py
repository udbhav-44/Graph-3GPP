from neo4j import GraphDatabase
import pandas as pd
import requests
import os
import zipfile
import shutil
from tqdm import tqdm 
import json

def clear_directory(path):
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isfile(item_path) or os.path.islink(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)

output_dir = "downloaded_docs"

os.makedirs(output_dir, exist_ok= True)
uri = "bolt:172.26.189.83:7687"
generate_uri = "http://172.26.189.83:4005/generate"
uname = "neo4j"
pswd = "login123"

driver = GraphDatabase.driver(uri, auth = (uname,pswd))

query = """
// Collect directly matched document IDs and their scores
CALL () {
  CALL db.index.fulltext.queryNodes("docIndex", $query)
  YIELD node, score
  WHERE $meeting IS NULL OR node.meeting_id CONTAINS $meeting
  RETURN
    collect(node.doc_id) AS direct_doc_ids,
    collect({doc_id: node.doc_id, score: score}) AS direct_docs
}
WITH direct_doc_ids, direct_docs  // <-- pass both forward

// Agenda matches (boost if linked to direct docs)
CALL (direct_doc_ids) {
  WITH direct_doc_ids  // <-- explicitly import into subquery
  CALL db.index.fulltext.queryNodes("agendaIndex", $query)
  YIELD node, score AS agenda_score
  MATCH (node)<-[:APPEARS_IN]-(d:Document)
  WITH d,
       CASE
         WHEN d.doc_id IN direct_doc_ids
           THEN agenda_score * 2.3    // boost if linked to direct doc
         ELSE agenda_score * 0.8
       END AS agenda_rel_score
  RETURN collect({doc_id: d.doc_id, score: agenda_rel_score}) AS agenda_docs
}
WITH direct_docs, agenda_docs  // <-- carry results forward

// Tech entity matches
CALL() {
  CALL db.index.fulltext.queryNodes("techEntityIndex", $query)
  YIELD node, score AS entity_score
  MATCH (d:Document)-[:MENTIONS]->(node)
  RETURN collect({doc_id: d.doc_id, score: entity_score * 0.7}) AS entity_docs
}
WITH direct_docs, agenda_docs, entity_docs

// Combine all document matches and compute total score
WITH direct_docs + agenda_docs + entity_docs AS all_docs
UNWIND all_docs AS doc_entry
WITH doc_entry.doc_id AS doc_id, sum(doc_entry.score) AS total_score
MATCH (d:Document {doc_id: doc_id})

// Apply title-based boosting
WITH d, total_score,
CASE
  WHEN d.title CONTAINS 'Feature Lead Summary' THEN total_score * 2.0
  WHEN d.title CONTAINS 'Feature Lead' THEN total_score * 1.5
  ELSE total_score
END AS boosted_score

// Return both raw and boosted scores for debugging
RETURN
  d.doc_id,
  d.title,
  d.source_path,
  d.meeting_id,
  d.release,
  total_score,
  boosted_score
ORDER BY boosted_score DESC
LIMIT 25;
"""
query_str = input("Enter your Query: ")
meeting = input("Entery the Meeting (Leave Empty if not sure): ")

params = {"query": query_str,
        "meeting": meeting}

with driver.session() as session:
    result = session.run(query,params)
    data = [record.data() for record in result]

df = pd.DataFrame(data)
clear_directory(output_dir)
clear_directory("/git_folder/udbhav/code/RAG/uploads")
# print(f"Getting the relevant documents.....and putting them in RAG...")
for i, row in tqdm(df.iterrows(), total = len(df), desc="Fetching the Documents"):
    url = row["d.source_path"]
    doc_id = row["d.doc_id"]
    title = row["d.title"].replace("/", "_")[:50]
    dest_path = os.path.join(output_dir, f"{doc_id} - {title}.zip")

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
        with zipfile.ZipFile(dest_path, 'r') as zip_ref:
          for member in zip_ref.namelist():
        # Skip macOS metadata and hidden files
            if member.startswith('__MACOSX/') or member.endswith('.DS_Store'):
              continue
            zip_ref.extract(member, "/git_folder/udbhav/code/RAG/uploads")
          os.remove(dest_path)
    except Exception as e:
        print(f"⚠️ Failed: {url} → {e}")


payload = {
    "query": query_str,
    "max_tokens": 5000,
    "num_docs": 10
}


try:
    print("Generating response...")
    response = requests.post(generate_uri, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()

    # Print or save result
    print(" Response:\n", json.dumps(result, indent=2))

except Exception as e:
    print(f" API request failed → {e}")



df.to_csv("search_results.csv")
driver.close()