import hashlib 
import os
from datetime import datetime
from pathlib import Path
from kor.extraction import create_extraction_chain
from kor import from_pydantic
import sys
from time import time
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from docling.document_converter import DocumentConverter
from DataModel.datamodel import DataModel, DataModelEncoder

converter = DocumentConverter()

def load_document(file_path: str):
    
    return converter.convert(file_path).document.export_to_markdown()

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
    
def extract_text(file_path):
    if is_file_cached(file_path):
        print(f"Info: File {file_path} is already cached.")
        cache_file_name = generate_cache_file_name(file_path)
        with open(cache_file_name, "r") as f:
            return f.read()
    else:
        data = load_document(file_path)
        cache_file_name = generate_cache_file_name(file_path)
        with open(cache_file_name, "w") as f:
            f.write(data)
        return data
    
    

def show_usage_and_exit():
    error_exit("Please pass name of directory or file to process.")
    
def enumerate_pdf_files(file_path):
    files_to_process = []
    # Users can pass a directory or a file name
    if os.path.isfile(file_path):
        if os.path.splitext(file_path)[1][1:].strip().lower() == 'docx':
            files_to_process.append(file_path)
    elif os.path.isdir(file_path):
        files = os.listdir(file_path)
        for file_name in files:
            if os.path.splitext(file_name)[1][1:].strip().lower() == 'docx':
                files_to_process.append(file_name)
    else:
        error_exit(f"Error. {file_path} should be a file or a directory.")
        
    return files_to_process


               
def extract_values_from_file(raw_file_data):
    # preamble = ("\n"
    #             "Your ability to extract and summarize the relevant 3GPP information accurately is essential for effective research"
    #             "Pay close attention to the language, structure, and any corss-refrences within the 3GPP data to ensure comprehensive and precise extraction of information."
    #             "Do not use prior knowledge or information from outside the context to answer the question "
    #             " Only use the information provided in the context to answer the questions.\n")
    # postamble = "Do not include any explanation in the reply. Only include the extracted information in the reply."
    # system_template = "{preamble}"
    # system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)
    # human_template = """{format_instructions}
    #                     {raw_file_data}
    #                     \n
    #                     {postamble}
    #                     """
    # human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    # parser = PydanticOutputParser(pydantic_object=DataModel)
    # # print(parser.get_format_instructions())
    # format_instructions = parser.get_format_instructions()
    
    

    # # compile chat template
    # chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])
    # request = chat_prompt.format_prompt(preamble=preamble,
    #                                     format_instructions=parser.get_format_instructions(),
    #                                     raw_file_data=raw_file_data,
    #                                     postamble=postamble).to_messages()
    
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0, top_p= 0.4)
    schema, validator = from_pydantic(DataModel)
    chain=create_extraction_chain(model, schema, encoder_or_encoder_class="json", validator=validator)
    
    # response = chain.run(raw_file_data)
    
    print("Querying model...")
    # result = model(request)
    response = chain.invoke(raw_file_data)
    # print("Response from model:")
    # print(response)
    return response
    # print(result.content)
    # return result.content


from datetime import datetime

def process_pdf_files(file_list):
    for file_path in file_list:
        raw_file_data = extract_text(file_path)
        # print(f"Extracted text for file {file_path}:\n{raw_file_data}")
        extracted_json = extract_values_from_file(raw_file_data)

        # Generate a timestamp-based filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file_path = f"output_{timestamp}.json"

        with open(json_file_path, "w") as f:
            f.write(json.dumps(extracted_json, indent=4, cls=DataModelEncoder))

        print(f"JSON data for {file_path} saved to {json_file_path}")


def main():
    start = time()
    load_dotenv(".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        error_exit("OPENAI_API_KEY environment variable not set")
    os.environ["OPENAI_API_KEY"] = api_key # type: ignore
    if len(sys.argv) < 2:
        show_usage_and_exit()

    print(f"Processing path {sys.argv[1]}...")
    file_list = enumerate_pdf_files(sys.argv[1])
    print(f"Processing {len(file_list)} files...")
    print(f"Processing first file: {file_list[0]}...")
    process_pdf_files(file_list)
    print(f"Processing took {time() - start} seconds.")

if __name__ == '__main__':
    main()
    