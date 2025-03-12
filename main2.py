import os
import concurrent.futures
import logging
from logging.handlers import RotatingFileHandler
from llama_index.llms.openai import OpenAI
from DataModel.datamodel import DataModel, DataModelEncoder
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
import json
from dotenv import load_dotenv
import time

# Configure advanced logging
def setup_logging():
    logger = logging.getLogger("file_processor")
    logger.setLevel(logging.DEBUG)  # Set the base logging level

    # Create handlers
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    file_handler = RotatingFileHandler("file_processor.log", maxBytes=5*1024*1024, backupCount=2)
    file_handler.setLevel(logging.DEBUG)

    # Create formatters and add them to handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

logger = setup_logging()

load_dotenv()

llm = OpenAI(model="gpt-4o")

def doc_loader(file_path: str):
    """Loads a document"""
    logger.info(f"Loading document: {file_path}")
    loader = UnstructuredWordDocumentLoader(file_path)
    data = loader.load()
    return data[0].page_content

def export_json(response, output_file_path: str):
    """Writes JSON output with the same name as the input file."""
    logger.info(f"Exporting JSON to: {output_file_path}")
    with open(output_file_path, "w") as f:
        json.dump(response,f, indent=4, cls=DataModelEncoder)

def list_files_in_directory(directory_path: str):
    """Lists all files in the given directory."""
    logger.info(f"Listing files in directory: {directory_path}")
    return [os.path.join(directory_path, f) for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))]

def process_file(file_path: str, output_directory: str, sllm):
    """Processes a single file and saves the output in the output directory."""
    try:
        # Load the document
        data = doc_loader(file_path)

        # Complete the data using the structured LLM
        response = sllm.complete(data)

        # Define the output file path in the output directory with the same name as the input file
        output_file_name = os.path.splitext(os.path.basename(file_path))[0] + ".json"
        output_file_path = os.path.join(output_directory, output_file_name)

        # Export the JSON response
        export_json(response.raw, output_file_path)
    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}", exc_info=True)

def process_files_in_directory(directory_path: str, output_directory: str, chunk_size: int = 10):
    """Processes all files in the given directory in parallel with chunking and saves output in the output directory."""
    # Initialize the structured LLM
    sllm = llm.as_structured_llm(DataModel)

    # Create the output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)

    # List all files in the directory
    files = list_files_in_directory(directory_path)

    # Use ProcessPoolExecutor to process files in parallel with chunking
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # Split files into chunks
        file_chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]

        # Submit tasks to the executor for each chunk
        futures = [executor.submit(process_chunk, chunk, output_directory, sllm) for chunk in file_chunks]

        # Wait for all tasks to complete
        concurrent.futures.wait(futures)

def process_chunk(file_chunk, output_directory, sllm):
    """Processes a chunk of files."""
    for file_path in file_chunk:
        process_file(file_path, output_directory, sllm)

def main():
    """Main function to execute the script."""
    start = time.time()
    directory_path = "source_docs"
    output_directory = "output"
    logger.info("Starting file processing.")
    process_files_in_directory(directory_path, output_directory)
    end = time.time()
    logger.info(f"Time taken: {end - start} seconds.")
    logger.info("File processing completed.")


if __name__ == "__main__":
    main()
