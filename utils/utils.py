import os
import sys
import hashlib
from pathlib import Path

from numpy import full


def error_exit(error_message):
    print(error_message)
    sys.exit(1)

def generate_cache_file_name(file_path: str, cache_dir: str = "cache"):
    """Generates a cache file name based on the first and last 4096 bytes of the file."""
    
    # Check if file is too small to process
    if os.path.getsize(file_path) < 4096:
        error_exit(f"File {file_path} too small to process.")  # Ensure error_exit is defined in utils

    # Read the first and last 4096 bytes
    with open(file_path, "rb") as f:
        first_block = f.read(4096)
        # seek to the last block
        f.seek(-4096, os.SEEK_END)
        last_block = f.read(4096)

    # Generate MD5 hashes for the first and last blocks
    first_md5_hash = hashlib.md5(first_block).hexdigest()
    last_md5_hash = hashlib.md5(last_block).hexdigest()

    # Ensure the cache directory exists
    os.makedirs(cache_dir, exist_ok=True)

    # Return the full path to the cache file
    return os.path.join(cache_dir, f"{first_md5_hash}_{last_md5_hash}.txt")


def is_file_cached(file_path: str, cache_dir: str = "cache") -> bool:
    """Checks if a file is already cached."""
    # Generate the cache file path
    cache_file_name = generate_cache_file_name(file_path, cache_dir)
    
    # Check if the cache file exists
    return Path(cache_file_name).is_file()
      
    

def show_usage_and_exit():
    error_exit("Please pass name of directory or file to process.")
    
def enumerate_files(file_path):
    files_to_process = []
    allowed_extensions = ['docx','doc']
    # Users can pass a directory or a file name
    if os.path.isfile(file_path):
        if os.path.splitext(file_path)[1][1:].strip().lower() in allowed_extensions:
            files_to_process.append(file_path)
    elif os.path.isdir(file_path):
        files = os.listdir(file_path)
        for file_name in files:
            if os.path.splitext(file_name)[1][1:].strip().lower() in allowed_extensions:
                full_path = os.path.join(file_path, file_name)
                files_to_process.append(full_path)
    else:
        error_exit(f"Error. {file_path} should be a file or a directory.")
        
    return files_to_process
