import os
import zipfile
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from llama_index.llms.deepseek import DeepSeek
from DataModel.datamodel import DataModel, DataModelEncoder
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
import json
from dotenv import load_dotenv
import time
from utils.utils import setup_logging
from typing import Union, Dict, Any
import tiktoken
import json
import shutil
import re
from pydantic import ValidationError


load_dotenv()
logger = setup_logging()
primary_llm = DeepSeek(model="deepseek-reasoner")
formatter_llm = DeepSeek(model="deepseek-chat")
# sllm = llm.as_structured_llm(DataModel)
PROCESSED_FILES_PATH = "processed_files.json"

def load_processed_files() -> set:
    if not os.path.exists(PROCESSED_FILES_PATH):
        return set()
    with open(PROCESSED_FILES_PATH, "r") as f:
        return set(json.load(f))

def save_processed_file(file_path: Path):
    processed = load_processed_files()
    processed.add(str(file_path.resolve()))
    with open(PROCESSED_FILES_PATH, "w") as f:
        json.dump(list(processed), f, indent=4)

def safe_complete(data: str) -> Union[Dict[str, Any], None]:
    try:
        # First attempt with structured LLM
        sllm = primary_llm.as_structured_llm(DataModel)
        response = sllm.complete(data)
        return response
    except Exception as e:
        logger.warning(f"Primary LLM structured output failed: {e}")
        
        try:
            # Create a more explicit formatting prompt with clear JSON structure
            reasoner_prompt = f"""
            Analyze this document and extract structured data according to the schema below.
            IMPORTANT: Ensure all JSON is properly formatted and all arrays are properly closed.
            
            Schema: {json.dumps(DataModel.model_json_schema(), indent=2)}
            
            Document: {data}
            
            Return ONLY valid, complete JSON.
            """
            
            # Get raw completion from primary LLM
            raw_response = primary_llm.complete(reasoner_prompt)
            
            # Extract JSON from the response (in case the LLM includes explanatory text)
            json_match = re.search(r'``````|(\{[\s\S]*\})', raw_response)
            if json_match:
                json_str = json_match.group(1) or json_match.group(2)
            else:
                json_str = raw_response
            
            # Clean up potential JSON issues
            json_str = json_str.strip()
            
            # Attempt to validate and fix common JSON issues
            try:
                formatted_json = json.loads(json_str)
                return {"raw": formatted_json}
            except json.JSONDecodeError as json_err:
                logger.warning(f"Initial JSON parsing failed: {json_err}")
                
                # Use formatter LLM as fallback for complex formatting issues
                formatting_prompt = f"""
                Fix this invalid JSON to strictly follow the schema:
                {json.dumps(DataModel.model_json_schema(), indent=2)}
                
                Invalid JSON:
                {json_str}
                
                Return ONLY the corrected JSON.
                """
                
                formatted_json_str = formatter_llm.complete(formatting_prompt)
                try:
                    formatted_json = json.loads(formatted_json_str)
                    return {"raw": formatted_json}
                except json.JSONDecodeError as second_err:
                    logger.error(f"Formatter failed to fix JSON: {second_err}")
                    return None
                    
        except Exception as formatter_err:
            logger.error(f"Formatter error: {formatter_err}")
            return None

        
def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
  
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        # Fallback to approximation method
        words = len(text.split())
        # Approximately 1.33 tokens per word (or 3/4 word per token)
        return int(words / 0.75)


def doc_loader(file_path: Path, max_tokens: int = 65536):

    logger.info(f"Loading document: {file_path}")
    loader = UnstructuredWordDocumentLoader(str(file_path))
    content = loader.load()[0].page_content
    
    # Count tokens
    token_count = count_tokens(content)
    within_limit = token_count < max_tokens
    
    if not within_limit:
        logger.warning(f"Document exceeds token limit: {file_path}, tokens: {token_count}")
    
    return content, token_count, within_limit


def export_json(response, output_file_path: Path):
    logger.info(f"Exporting JSON to: {output_file_path}")
    with output_file_path.open("w") as f:
        json.dump(response, f, indent=4, cls=DataModelEncoder)

def convert_local_path_to_3gpp_url(local_path: Path) -> str:
    try:
        path_parts = local_path.resolve().parts
        idx = path_parts.index("DATA1")
        ftp_path = "/".join(path_parts[idx + 1:])  # Skip "DATA" itself
        return f"https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_119/Docs/{ftp_path}"
    except ValueError:
        logger.warning(f"Path does not contain 'DATA': {local_path}")
        return str(local_path)

def extract_doc_files_from_zip(zip_path: Path):
    extracted_paths = []
    temp_dirs = []  # Keep track of temporary directories created
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if "__MACOSX" in file_info.filename or file_info.filename.startswith("._"):
                        continue
                    
                if file_info.filename.lower().endswith(('.doc', '.docx')):
                    temp_dir = tempfile.mkdtemp()
                    temp_dirs.append(temp_dir)
                    extracted_path = zip_ref.extract(file_info, temp_dir)
                    extracted_paths.append(Path(extracted_path))
    except zipfile.BadZipFile:
        logger.warning(f"Bad zip file encountered: {zip_path}")
        
    return extracted_paths, temp_dirs

def process_zip(zip_file: Path, output_directory: Path, processed_files: set, max_tokens: int = 65536):
    try:
        if str(zip_file.resolve()) in processed_files:
            logger.info(f"Skipping already processed zip: {zip_file}")
            return

        doc_files, temp_dirs = extract_doc_files_from_zip(zip_file)
        if not doc_files:
            logger.warning(f"No .doc/.docx files found in: {zip_file}")
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir, ignore_errors=True)
            return

        zip_url = convert_local_path_to_3gpp_url(zip_file)
        successful_exports = 0

        for doc_file in doc_files:
            try:
                # Get content and check token count
                content, token_count, within_limit = doc_loader(doc_file, max_tokens)
                
                # Skip documents that exceed the token limit
                if not within_limit:
                    logger.info(f"Skipping document with {token_count} tokens (limit: {max_tokens}): {doc_file}")
                    continue

                # Process documents that are within the token limit
                response = safe_complete(content)

                if response is None:
                    logger.warning(f"No valid response for: {doc_file}")
                    continue

                response_dict = json.loads(json.dumps(response.raw, cls=DataModelEncoder))

                for doc in response_dict.get("documents", []):
                    doc["source_path"] = zip_url
                    # Optionally add token count for reference
                    doc["token_count"] = token_count

                output_file_path = output_directory / (doc_file.stem + ".json")
                export_json(response_dict, output_file_path)
                successful_exports += 1

            except Exception as e:
                logger.error(f"Error processing document in {zip_file}: {e}", exc_info=True)
            finally:
                # Clean up the temporary directory for this document
                temp_dir = doc_file.parent
                shutil.rmtree(temp_dir, ignore_errors=True)

        # Only mark the zip as processed if at least one file was successfully exported
        if successful_exports > 0:
            save_processed_file(zip_file)
            logger.info(f"Finished processing zip: {zip_file}")
        else:
            logger.warning(f"No successful exports from zip: {zip_file}")

    except Exception as e:
        logger.error(f"Error processing zip file {zip_file}: {e}", exc_info=True)



def list_zip_files(directory_path: Path):
    logger.info(f"Listing zip files in directory: {directory_path}")
    return [file for file in directory_path.iterdir() if file.is_file() and file.suffix == ".zip"]

def process_files_in_directory(directory_path: Path, output_directory: Path, max_tokens: int = 65536, max_threads: int = 60):
    os.makedirs(output_directory, exist_ok=True)
    zip_files = list_zip_files(directory_path)
    processed_files = load_processed_files()

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_file = {
            executor.submit(process_zip, zip_file, output_directory, processed_files, max_tokens): zip_file
            for zip_file in zip_files
        }

        for future in as_completed(future_to_file):
            file = future_to_file[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Failed processing {file}: {e}")

def main():
    start = time.time()
    directory_path = Path("/git_folder/udbhav/DATA1/")
    output_directory = Path("output1")
    max_tokens = 64000  # Set your token limit here

    logger.info("Starting zip file processing.")
    process_files_in_directory(directory_path, output_directory, max_tokens)

    end = time.time()
    logger.info(f"Total time taken: {end - start:.2f} seconds.")
    logger.info("Zip file processing completed.")


if __name__ == "__main__":
    main()
