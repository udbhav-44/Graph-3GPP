# Graph-3GPP
Repository for the Literature Graph for 3GPP data 

## What to do 
1. Use a Document Parser (a simple or advanced) to read the Documents
2. Use that Document content to extract the structured infomation based on the DATAMODEL 
3. Export a JSON per file



## Current Directory -

- 
- /git_folder/udbhav/DATA/tsg_ran/WG1_RL1/TSGR1_119/Docs/
- List of files in processed_files_list.txt






### 

1. https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_119
2. TSGR1_118b -> Docs + Inbox (Agenda + Chair Notes + David_sessions + Xiadong_sessions + Drafts)
3. TSGR1_118
4. TSGR1_117





docker run --name neo4j \
  --memory=64g \
  --memory-swap=96g \
  --cpus="24" \
  -p 7474:7474 -p 7687:7687 \
  -p 2004:2004 \
  -e NEO4J_AUTH=neo4j/password \
  -e NEO4J_server_memory_heap_initial__size=32g \
  -e NEO4J_server_memory_heap_max__size=48g \
  -e NEO4J_server_memory_pagecache_size=16g \
  -e NEO4J_dbms_security_procedures_unrestricted=apoc.* \
  -e NEO4J_dbms_security_procedures_allowlist=apoc.* \
  -e NEO4J_apoc_export_file_enabled=true \
  -e NEO4J_apoc_import_file_enabled=true \
  -e NEO4J_apoc_import_file_use__neo4j__config=true \
  -v $PWD/plugins:/plugins \
  -v /var/lib/docker/volumes/neo4j_data/_data:/data \
  -v /var/lib/docker/volumes/neo4j_logs/_data:/logs \
  -v /git_folder/udbhav/code/Graph-3GPP/neo4j_csv_output:/import \
  neo4j:latest


docker run --rm -e NEO4J_AUTH=none -p 7474:7474 -v $PWD/plugins:/plugins -p 7687:7687 neo4j:4.4