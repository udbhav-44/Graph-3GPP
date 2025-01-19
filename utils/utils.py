import os
import sys
import hashlib
from pathlib import Path

from numpy import full


def error_exit(error_message):
    print(error_message)
    sys.exit(1)

def generate_cache_file_name(file_path):
    # For our use case, PDFs won't be less than 4096, practically speaking.
    if os.path.getsize(file_path) < 4096:
        error_exit("File too small to process.")
    with open(file_path, "rb") as f:
        first_block = f.read(4096)
        # seek to the last block
        f.seek(-4096, os.SEEK_END)
        f.read(4096)
        last_block = f.read(4096)

    first_md5_hash = hashlib.md5(first_block).hexdigest()
    last_md5_hash = hashlib.md5(last_block).hexdigest()
    return f"/tmp/{first_md5_hash}_{last_md5_hash}.txt"


def is_file_cached(file_path):
    cache_file_name = generate_cache_file_name(file_path)
    cache_file = Path(cache_file_name)
    if cache_file.is_file():
        return True
    else:
        return False
      
    

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
