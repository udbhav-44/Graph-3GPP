import asyncio
import os
from datetime import datetime
from kor.extraction import create_extraction_chain
from kor import from_pydantic
import sys
from time import time
import json
import aiofiles
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from docling.document_converter import DocumentConverter
from DataModel.datamodel import DataModel, DataModelEncoder
from utils.utils import error_exit, generate_cache_file_name, is_file_cached, show_usage_and_exit, enumerate_files
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
import logging
import psutil
from concurrent.futures import ThreadPoolExecutor


# Configure logging
logging.basicConfig(
    filename='processing.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# Global Constants
OUTPUT_DIR = "output"
CACHE_DIR = "cache"
SOURCE_DIR = "source_docs"
CHUNK_SIZE = 100  # Adjust batch size based on system performance


def monitor_system():
    """Monitors and prints system resource usage."""
    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    disk = psutil.disk_usage('/')
    disk_usage = disk.percent
    
    logging.info(f"CPU Usage: {cpu_usage}% | Memory Usage: {memory_usage}% | Disk Usage: {disk_usage}%")

# def log_performance(start_time):
#     elapsed_time = time() - start_time
#     logging.info(f"Batch processed in {elapsed_time:.2f} seconds.")
    
    
    
def load_document(file_path: str):
    """Loads a document and caches it if not already cached."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file_name = generate_cache_file_name(file_path,CACHE_DIR)
    if is_file_cached(file_path,CACHE_DIR):
        logging.info(f"File {file_path} is already cached.")
        with open(cache_file_name, "r") as f:
            return f.read()

    converter = DocumentConverter()
    data = converter.convert(file_path).document.export_to_markdown()
    with open(cache_file_name, "w") as f:
        f.write(data)
    return data


               
def extract_values_from_file(raw_file_data):
    """Uses a model to extract structured data from the raw file data."""
    try:
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0.5, top_p= 0.4)
        schema, validator = from_pydantic(DataModel)
        chain=create_extraction_chain(model, schema, encoder_or_encoder_class="json", validator=validator)
        
        logging.info("Querying model...")

        response = chain.invoke(raw_file_data)
    
        return response
    except Exception as e:
        logging.error(f"Error extracting values from file: {e}")
        raise
 

async def async_process_file(file_path: str):
    """Processes a single file: extracts text, queries the model, and writes JSON output."""
    try:
        raw_file_data = load_document(file_path)
        extracted_json = extract_values_from_file(raw_file_data)

        # Write JSON output
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        base_name = os.path.basename(file_path).split('.')[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(OUTPUT_DIR, f"{base_name}_{timestamp}.json")
        async with aiofiles.open(output_file, "w") as f:
            await f.write(json.dumps(extracted_json, indent=4, cls=DataModelEncoder))

        logging.info(f"Processed file: {file_path}")
    except Exception as e:
        logging.error(f"Error processing file {file_path}: {e}")
        
def process_file(file_path: str):
    """Runs the async processing function in an event loop."""
    asyncio.run(async_process_file(file_path))


def process_files_batch(file_batch: list):
    """Processes a batch of files using multithreading."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with ThreadPoolExecutor(max_workers=cpu_count() * 2) as executor:
        tasks = [
            loop.run_in_executor(executor, process_file, file)
            for file in file_batch
        ]
        loop.run_until_complete(asyncio.gather(*tasks))


def process_files_in_parallel(file_list: list):
    """Processes all files in parallel using multiprocessing."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logging.info(f"Processing {len(file_list)} files in parallel...")

    num_workers = min(cpu_count(), len(file_list) // CHUNK_SIZE + 1)
    with Pool(num_workers) as pool:
        for i in tqdm(range(0, len(file_list), CHUNK_SIZE), desc="Processing Batches"):
            chunk = file_list[i:i + CHUNK_SIZE]
            pool.apply_async(process_files_batch, args=(chunk,))
            monitor_system()

        pool.close()
        pool.join()
        


def main():
    """Main function to process all files from source directory."""
    start_time = time()

    # Load environment variables
    load_dotenv(".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logging.error("OPENAI_API_KEY environment variable not set.")
        return
    os.environ["OPENAI_API_KEY"] = api_key

    # Collect files from source directory
    file_list = [
        os.path.join(SOURCE_DIR, file)
        for file in os.listdir(SOURCE_DIR)
        if os.path.isfile(os.path.join(SOURCE_DIR, file))
    ]
    logging.info(f"Found {len(file_list)} files in {SOURCE_DIR}.")

    # Process files
    process_files_in_parallel(file_list)

    elapsed_time = time() - start_time
    logging.info(f"Processing completed in {elapsed_time:.2f} seconds.")


if __name__ == "__main__":
    main()
    