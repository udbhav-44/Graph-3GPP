# Graph-3GPP

**Graph-3GPP** is a comprehensive pipeline for building a specific Knowledge Graph from 3GPP meeting documents. It processes unstructured `.doc` and `.docx` files (contained in zip archives), extracts structured metadata and relationships using Large Language Models (DeepSeek), and facilitates import into a Neo4j graph database for advanced querying and RAG (Retrieval-Augmented Generation) applications.

## Key Features

* **Automated Document Processing**: Extracts content from nested zip archives of 3GPP meeting documents.
* **Intelligent Extraction**: Uses **DeepSeek** LLMs (Reasoner & Chat) to extract structured data according to a strict schema.
* **Robust Data Model**: Extracts entities such as **Documents**, **Authors/Contributors**, **Meetings**, **Agendas**, **Working Groups**, and **Technology Entities**.
* **Relationship Mapping**: Captures relationships like *Authored By*, *Mentions*, *Belongs To* (Working Group), *References*, and *Appears In* (Agenda).
* **Graph Database Ready**: Converts extracted JSON data into normalized CSV files ready for bulk import into **Neo4j**.
* **RAG & Querying**: Includes scripts to query the graph and retrieve relevant source documents for analysis.

## Project Structure

```text
Graph-3GPP/
├── DataModel/
│   └── datamodel.py          # Pydantic models definitions (Schema)
├── Process_3GPP_Docs.py      # Main script to process raw documents -> JSON
├── generate_csv.py           # Converts processed JSONs -> Neo4j CSVs
├── query_graph.py            # RAG/Search interface for the Graph
├── requirements.txt          # Python dependencies
├── README.md                 # Project documentation
├── .env                      # Environment variables (API keys)
└── neo4j_csv_output2/        # Generated CSV files (Output)
```

## Prerequisites

* Python 3.8+
* [Neo4j](https://neo4j.com/) (Docker reference provided below)
* **DeepSeek API Key** (for LLM processing)

## Installation

1. **Clone the repository**:

    ```bash
    git clone https://github.com/udbhav-44/Graph-3GPP.git
    cd Graph-3GPP
    ```

2. **Install dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

3. **Configure Environment**:
    Create a `.env` file in the root directory and add your keys:

    ```ini
    DEEPSEEK_API_KEY=your_api_key_here
    ```

## Usage

### 1. Process Documents

The `Process_3GPP_Docs.py` script reads `.zip` files containing Word documents, processes them with LLMs, and saves JSON outputs.

* **Configuration**: Edit the `main()` function in `Process_3GPP_Docs.py` to set your input directory (`directory_path`) and output directory (`output_directory`).
* **Run**:

    ```bash
    python Process_3GPP_Docs.py
    ```

### 2. Generate CSVs

Convert the processed JSON files into CSVs suitable for Neo4j import.

* **Run**:

    ```bash
    python generate_csv.py
    ```

  * Input: `Results/` (default)
  * Output: `./neo4j_csv_output2` (default)

### 3. Neo4j Setup & Import

You can run Neo4j using Docker. The following command mounts the CSV output directory to the container's import folder.

```bash
docker run --name neo4j \
  --memory=64g \
  --memory-swap=96g \
  --cpus="24" \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  -e NEO4J_apoc_export_file_enabled=true \
  -e NEO4J_apoc_import_file_enabled=true \
  -e NEO4J_dbms_security_procedures_unrestricted=apoc.* \
  -v $PWD/plugins:/plugins \
  -v /var/lib/docker/volumes/neo4j_data/_data:/data \
  -v /git_folder/udbhav/code/Graph-3GPP/neo4j_csv_output2:/import \
  neo4j:latest
```

Once running, you can use `LOAD CSV` commands or `neo4j-admin import` to load the data from the `/import` directory.

### 4. Query & RAG

Use `query_graph.py` to perform full-text searches and retrieve context from the graph.

* **Configuration**: Update Neo4j connection details (`uri`, `uname`, `pswd`) in `query_graph.py`.
* **Run**:

    ```bash
    python query_graph.py
    ```

##  Data Model

The extraction logic is defined in `DataModel/datamodel.py`.

* **Nodes**:
  * `Document`: The core 3GPP document.
  * `Contributor`: Authors or organizations.
  * `WorkingGroup`: Committees (e.g., RAN WG1).
  * `Meeting`: Specific meeting instances.
  * `Agenda`: Agenda items.
  * `TechnologyEntity`: Extracted concepts (e.g., "LTE", "NR").

* **Relationships**:
  * `AUTHORED`: Contributor -> Document
  * `MENTIONS`: Document -> TechnologyEntity
  * `BELONGS_TO`: Document -> WorkingGroup
  * `APPEARS_IN`: Document -> Agenda
  * `REFERENCES`: Document -> Document


