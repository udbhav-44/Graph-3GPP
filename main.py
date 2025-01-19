import asyncio
import os
from datetime import datetime
from kor.extraction import create_extraction_chain
from kor import from_pydantic
import sys
from time import time
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from docling.document_converter import DocumentConverter
from DataModel.datamodel import DataModel, DataModelEncoder
from utils.utils import error_exit, generate_cache_file_name, is_file_cached, show_usage_and_exit, enumerate_files
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
import logging
import psutil


# Configure logging
logging.basicConfig(
    filename='processing.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def monitor_system():
    """Monitors and prints system resource usage."""
    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    disk = psutil.disk_usage('/')
    disk_usage = disk.percent
    
    logging.info(f"CPU Usage: {cpu_usage}% | Memory Usage: {memory_usage}% | Disk Usage: {disk_usage}%")

def log_performance(start_time):
    elapsed_time = time() - start_time
    logging.info(f"Batch processed in {elapsed_time:.2f} seconds.")
    
    
    

async def load_document(file_path: str):
    """Loads a document and caches it if not already cached."""
    cache_file_name = generate_cache_file_name(file_path)
    if is_file_cached(file_path):
        print(f"Info: File {file_path} is already cached.")
        with open(cache_file_name, "r") as f:
            return f.read()
    else:
        converter = DocumentConverter()
        data = converter.convert(file_path).document.export_to_markdown()
        with open(cache_file_name, "w") as f:
            f.write(data)
        return data


def extract_text(file_path):
    """Extracts text from the file or retrieves it from the cache."""
    return asyncio.run(load_document(file_path))

               
def extract_values_from_file(raw_file_data):
    """Uses a model to extract structured data from the raw file data."""
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0.5, top_p= 0.4)
    schema, validator = from_pydantic(DataModel)
    chain=create_extraction_chain(model, schema, encoder_or_encoder_class="json", validator=validator)
    
    print("Querying model...")

    response = chain.invoke(raw_file_data)
   
    return response
 

def process_file(file_path):
    """Processes a single file: extracts text, queries the model, and writes JSON output."""
    try:
        # Extract raw text
        raw_file_data = extract_text(file_path)

        # Extract structured data
        extracted_json = extract_values_from_file(raw_file_data)

        # Generate output file path
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.basename(file_path).split('.')[0]  # File name without extension
        json_file_name = f"{base_name}_{timestamp}.json"
        json_file_path = os.path.join(output_dir, json_file_name)

        # Write extracted JSON to output
        with open(json_file_path, "w") as f:
            f.write(json.dumps(extracted_json, indent=4, cls=DataModelEncoder))

        logging.info(f"JSON data for {file_path} saved to {json_file_path}")

    except Exception as e:
        logging.error(f"Error processing file {file_path}: {e}")

def process_files_in_parallel(file_list):
    """Processes a list of files using multiprocessing."""
    num_workers = min(len(file_list), cpu_count())  # Use all available cores or limit to file count
    logging.info(f"Using {num_workers} worker processes.")

    with Pool(num_workers) as pool:
        chunk_size = 100  # Set batch size to process 100 files per batch
        for i in range(0, len(file_list), chunk_size):
            chunk = file_list[i:i + chunk_size]
            pool.map(process_file, chunk)
            monitor_system()
            log_performance(time())



def main():
    start = time()

    load_dotenv(".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        error_exit("OPENAI_API_KEY environment variable not set")
    os.environ["OPENAI_API_KEY"] = api_key  # type: ignore

    # Parse input arguments
    if len(sys.argv) < 2:
        show_usage_and_exit()

    input_path = sys.argv[1]
    logging.info(f"Processing path {input_path}...")

    file_list = enumerate_files(input_path)
    logging.info(f"Found {len(file_list)} files.")

    process_files_in_parallel(file_list)

    logging.info(f"Processing completed in {time() - start:.2f} seconds.")

if __name__ == '__main__':
    main()
    