from typing import Any
from neo4j import GraphDatabase
import pandas as pd
import requests
import os
import zipfile
import shutil
import json
import gradio as gr
from datetime import datetime
import urllib.parse
import logging
from spire.doc import Document, FileFormat


FEEDBACK_FILE = "feedback_log.csv"
LOG_FILE = "beta_testing.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)

def clear_directory(path):

    """Clear all files and directories in the specified path"""
    logging.info(f"Clearing directory: {path}")
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        return
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isfile(item_path) or os.path.islink(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)


def format_response(response_text):
    """Format JSON or text responses nicely"""
    logging.info(f"Formatting response: {response_text}")
    try:
        data = json.loads(response_text)
        formatted = "### Generated Response\n\n"
        if isinstance(data, dict):
            for k, v in data.items():
                formatted += f"**{k}**:\n{v}\n\n"
        elif isinstance(data, list):
            for i, item in enumerate(data, start=1):
                formatted += f"**Result {i}:**\n{json.dumps(item, indent=2)}\n\n"
        else:
            formatted = str(data)
        return formatted
    except json.JSONDecodeError:
        # Fallback: raw text as markdown
        return f"### 🤖 Generated Response\n\n{response_text}"


def save_feedback(name, query, score, remarks, ai_response, progress=gr.Progress()):
    """Save user feedback persistently"""
    logging.info(f"Saving feedback: {name}, {query}, {score}, {remarks}, {ai_response}")
    import time
    progress(0.3, desc="Processing feedback...")
    time.sleep(0.2)  # Small delay to show progress
    logging.info(f"Processing feedback: {name}, {query}, {score}, {remarks}, {ai_response}")
    entry = {
        "timestamp": datetime.now().isoformat(timespec='seconds'),
        "name": name,
        "query": query,
        "score": score,
        "remarks": remarks,
        "ai_response": ai_response
    }

    progress(0.7, desc="Saving to file...")
    time.sleep(0.2)  # Small delay to show progress
    # Append to CSV
    df = pd.DataFrame([entry])
    if os.path.exists(FEEDBACK_FILE):
        df.to_csv(FEEDBACK_FILE, mode='a', header=False, index=False)
    else:
        df.to_csv(FEEDBACK_FILE, index=False)

    progress(1.0, desc="Complete!")
    time.sleep(0.1)  # Small delay to show completion
    return None
    # return f"✅ Feedback saved for query: {query}"


def search_and_generate(name_input,query_str, meeting_id, progress=gr.Progress()):
    """Main function that searches Neo4j, downloads documents, and generates response"""
    output_dir = "downloaded_docs"
    uri = "bolt://172.26.189.83:7687"
    uploads_dir = "/git_folder/udbhav/code/RAG/uploads"
    generate_uri = "http://172.26.189.83:4005/generate"
    stats_uri = "http://172.26.189.83:4004/v1/statistics"
    uname = "neo4j"
    pswd = "login123"
    logging.info(f"Received search request: {name_input}, {query_str}, {meeting_id}")
    progress(0, desc="Initializing...")
    logging.info(f"Starting search process: {query_str}, {meeting_id}")
    yield None, None  # matches (df_output, response_output)

    os.makedirs(output_dir, exist_ok=True)
    clear_directory(output_dir)
    clear_directory("/git_folder/udbhav/code/RAG/uploads")
    logging.info(f"Directories prepared: {output_dir}, /git_folder/udbhav/code/RAG/uploads")
    progress(0.1, desc="Connecting to database...")

    query = """
    CALL () {
      CALL db.index.fulltext.queryNodes("docIndex", $query)
      YIELD node, score
      WHERE $meeting IS NULL OR node.meeting_id CONTAINS $meeting
      RETURN
        collect(node.doc_id) AS direct_doc_ids,
        collect({doc_id: node.doc_id, score: score}) AS direct_docs
    }
    WITH direct_doc_ids, direct_docs
    CALL (direct_doc_ids) {
      WITH direct_doc_ids
      CALL db.index.fulltext.queryNodes("agendaIndex", $query)
      YIELD node, score AS agenda_score
      MATCH (node)<-[:APPEARS_IN]-(d:Document)
      WITH d,
           CASE
             WHEN d.doc_id IN direct_doc_ids THEN agenda_score * 2.3
             ELSE agenda_score * 0.8
           END AS agenda_rel_score
      RETURN collect({doc_id: d.doc_id, score: agenda_rel_score}) AS agenda_docs
    }
    WITH direct_docs, agenda_docs
    CALL() {
      CALL db.index.fulltext.queryNodes("techEntityIndex", $query)
      YIELD node, score AS entity_score
      MATCH (d:Document)-[:MENTIONS]->(node)
      RETURN collect({doc_id: d.doc_id, score: entity_score * 0.7}) AS entity_docs
    }
    WITH direct_docs, agenda_docs, entity_docs
    WITH direct_docs + agenda_docs + entity_docs AS all_docs
    UNWIND all_docs AS doc_entry
    WITH doc_entry.doc_id AS doc_id, sum(doc_entry.score) AS total_score
    MATCH (d:Document {doc_id: doc_id})
    WITH d, total_score,
    CASE
      WHEN d.title CONTAINS 'Feature Lead Summary' THEN total_score * 2.0
      WHEN d.title CONTAINS 'Feature Lead' THEN total_score * 1.5
      ELSE total_score
    END AS boosted_score
    RETURN
      d.doc_id,
      d.title,
      d.source_path,
      d.meeting_id,
      d.release,
      total_score,
      boosted_score
    ORDER BY boosted_score DESC
    LIMIT 15;
    """

    try:
        driver = GraphDatabase.driver(uri, auth=(uname, pswd))
        logging.info(f"Connected to Neo4j: {uri}")
        progress(0.2, desc="Executing Neo4j query...")

        meeting = meeting_id.strip() if meeting_id and meeting_id.strip() else None
        params = {"query": query_str, "meeting": meeting}

        with driver.session() as session:
            result = session.run(query, params)
            data = [record.data() for record in result]

        driver.close()
        logging.info(f"Found {len(data)} documents")

        if not data:
            progress(1.0, desc="No results found")
            yield None, "⚠️ No matching documents found."
            return

        df = pd.DataFrame(data)
        progress(0.3, desc="Downloading matched documents...")
        yield df, None

        import concurrent.futures

        def download_and_extract(row):
            url, doc_id, title = row._3, row._1, row._2[:50].replace("/", "_")
            dest_path = os.path.join(output_dir, f"{doc_id} - {title}.zip")
            temp_extract_dir = os.path.join("/tmp/extracted_docs", str(doc_id))
            os.makedirs(temp_extract_dir, exist_ok=True)
            

            try:
                encoded_url = urllib.parse.quote(url, safe=':/')
                r = requests.get(encoded_url, timeout=20)
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    f.write(r.content)
                with zipfile.ZipFile(dest_path, 'r') as zip_ref:
                    for member in zip_ref.namelist():
                        if not (member.startswith('__MACOSX/') or member.endswith('.DS_Store')):
                            
                            zip_ref.extract(member, temp_extract_dir)
                os.remove(dest_path)
                for root, _, files in os.walk(temp_extract_dir):
                    for fname in files:
                        src_path = os.path.join(root, fname)
                        dst_path = os.path.join(uploads_dir, fname)

                        # --- Handle .doc/.docm securely ---
                        if fname.lower().endswith((".doc", ".docm")):
                            try:
                                document = Document()
                                document.LoadFromFile(src_path)

                                if document.IsContainMacro:
                                    logging.info(f"[{fname}] contains macros — removing...")
                                    document.ClearMacros()

                                # Save as .docx clean file in uploads/
                                clean_path = os.path.splitext(dst_path)[0] + ".docx"
                                document.SaveToFile(clean_path, FileFormat.Docx2016)
                                document.Close()

                                logging.info(f"Cleaned and moved safely: {clean_path}")
                            except Exception as e:
                                logging.error(f"Spire.Doc failed for {fname}: {e}")

                        else:
                            # Safe file — move directly
                            safe_dst = os.path.join(uploads_dir, fname)
                            shutil.move(src_path, safe_dst)

                # Remove temp directory
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
                return (title, None)
            except Exception as e:
                logging.error(f"Error downloading {title}: {e}")
                return (title, str(e))

        download_errors = []
        max_workers = min(20, len(df))  # limit threads to 10 or number of docs

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(download_and_extract, row): row for row in df.itertuples()}
            total = len(futures)
            for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                title, err = future.result()
                if err:
                    download_errors.append(f"{title}: {err}")
                progress(0.3 + (i / total) * 0.3, desc=f"Downloading {i}/{total}")

        logging.info(f"Downloaded {len(df) - len(download_errors)}/{len(df)} documents successfully")


        import time
        progress(0.65, desc="Waiting for service readiness...")

        start_time = time.time()
        max_wait = 300  # 5 minutes
        ready = False
        while time.time() - start_time < max_wait:
            try:
                resp = requests.get(stats_uri, timeout=5)
                if resp.status_code == 200:
                    ready = True
                    logging.info("AI service ready.")
                    break
                else:
                    logging.info(f"AI not ready, status={resp.status_code}")
            except Exception as e:
                logging.info(f"AI service check failed: {e}")
            time.sleep(5)  # retry every 5 seconds

        if not ready:
            msg = f"❌ Timeout: AI service not ready after {max_wait/60:.1f} minutes."
            logging.error(msg)
            yield df, msg
            return

        # ✅ Call AI generator after readiness confirmed
        progress(0.7, desc="Generating AI response...")
        payload = {"query": query_str, "max_tokens": 5000, "num_docs": 10}

        try:
            response = requests.post(generate_uri, json=payload, timeout=90)
            response.raise_for_status()
            formatted_response = format_response(json.dumps(response.json()))
        except Exception as e:
            formatted_response = f"❌ Failed to generate response: {e}"
            logging.error(formatted_response)

        csv_path = "search_results.csv"
        df.to_csv(csv_path, index=False)
        logging.info(f"Saved results to {csv_path}")

        progress(1.0, desc="Complete!")
        yield df, formatted_response

    except Exception as e:
        logging.error(f"Fatal error in search_and_generate: {e}")
        yield None, f"❌ Error: {e}"



# ----------- GRADIO UI -----------
with gr.Blocks(title="Wisdom Lab 3GPP RAG", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 3GPP Document Search & RAG Beta Testing")
    gr.Markdown("## Please provide feedback on the query and answer")
    gr.Markdown('### **Only the documents of Meetings RAN1-116 - 119 are indexed (including bis)**')

    with gr.Row():
        with gr.Column(scale=2):
            name_input = gr.Textbox(label=" Name", placeholder="Enter your name")
            query_input = gr.Textbox(label=" Query", lines=3, placeholder="Enter your query")
            meeting_input = gr.Textbox(label=" Meeting ID (Optional)", placeholder="Leave empty if not sure")
            search_btn = gr.Button(" Search & Generate", variant="primary", size="lg")
        with gr.Column(scale=1):
            gr.Markdown("### Feedback")
            
            score_input = gr.Slider(0, 10, step=1, label="Rate the answer (0–10)")
            remarks_input = gr.Textbox(label="Remarks", placeholder="Any comments...")
            submit_feedback_btn = gr.Button(" Submit Feedback", variant="primary", size="lg")
            
    
    gr.Markdown("---")
    response_output = gr.Markdown(label="🤖 AI Response")
    df_output = gr.DataFrame(label=" Search Results", interactive=False)
    
    search_btn.click(
        fn=search_and_generate,
        inputs=[name_input,query_input, meeting_input],
        outputs=[ df_output, response_output],
        queue=True
    )

    submit_feedback_btn.click(
        fn=save_feedback,
        inputs=[name_input, query_input, score_input, remarks_input, response_output],
        outputs=[],
        queue=True,
        show_progress='full'
    )

if __name__ == "__main__":
    demo.queue(max_size=15)
    demo.launch(server_name="0.0.0.0", server_port=7860, debug=True)
