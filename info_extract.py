import hashlib 
import os
from datetime import datetime
from pydoc import Doc
from typing import List, Optional
from pathlib import Path
# from turtle import title
import sys

import requests
from dotenv import load_dotenv
from langchain.prompts import SystemMessagePromptTemplate, ChatPromptTemplate, \
    HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from docling.document_converter import DocumentConverter

from pydantic import BaseModel
from typing import List, Optional

# Node Models
class Author(BaseModel):
    name: str = Field(description="")
    aliases: List[str] = Field(description="")

class Document(BaseModel):
    doc_id: str = Field(description="")
    title: str = Field(description="")
    release: str = Field(description="")
    type: Optional[str] = Field(description="")
    tags: Optional[List[str]] = Field(description="")
    summary: str = Field(description="")
    topic: Optional[str] = Field(description="")
    keywords: List[str] = Field(description="")
    agenda_id: Optional[str] = Field(description="")
    meeting_id: Optional[str] = Field(description="")
    status: Optional[str] = Field(description="")
    agenda_id: Optional[str] = Field(description="")
    working_groups: List[str] = [] # Reference to WorkingGroup 

class TechnologyEntity(BaseModel):
    canonical_name: str = Field(description="")
    aliases: List[str] = Field(description="")
    description: Optional[str] = Field(description="")

class WorkingGroup(BaseModel):
    id: str = Field(description="")
    name: str = Field(description="")
    description: Optional[str] = Field(description="")

class Meeting(BaseModel):
    meeting_id: str = Field(description="")
    venue: str = Field(description="")
    date: str = Field(description="")
    wg: str = Field(description="")  # Reference to Working Group
    topic: Optional[str] = Field(description="")

class Agenda(BaseModel):
    agenda_id: str = Field(description="")
    meeting_id: str = Field(description="")
    topic: Optional[str] = Field(description="")
    description: Optional[str] = Field(description="")

# Edge Models
class Mentions(BaseModel):
    doc_id: str = Field(description="")
    entity_name: str  = Field(description="") # Reference to TechnologyEntity
    context: Optional[str] = Field(description="")
    frequency : Optional[int] = Field(description="")

class Authored(BaseModel):
    doc_id: str = Field(description="")
    author_name: str = Field(description="") # Reference to Author
    contribution_type: Optional[str] = Field(description="")

class BelongsTo(BaseModel):
    doc_id: str = Field(description="")
    wg_name: str = Field(description="") # Reference to WorkingGroup
    role_in_group: Optional[str] = Field(description="") # Role of the document in the working group

class References(BaseModel):
    source_doc_id: str = Field(description="")
    target_doc_id: str = Field(description="")
    type_of_reference: Optional[str]  = Field(description="")# Type of reference (e.g. citation, appendix, related work, etc.)

class AppearsIn(BaseModel):
    agenda_id: str = Field(description="")
    page_range: Optional[str] = Field(description="")
    doc_id: str = Field(description="")

# Main Data Model
class DataModel(BaseModel):
    authors: List[Author] = Field(description="")
    documents: List[Document] = Field(description="")
    technology_entities: List[TechnologyEntity] = Field(description="")
    working_groups: List[WorkingGroup] = Field(description="")
    meetings: List[Meeting] = Field(description="")
    agendas: List[Agenda] = Field(description="")
    mentions: List[Mentions] = Field(description="")
    authored: List[Authored] = Field(description="")
    belongs_to: List[BelongsTo] = Field(description="")
    references: List[References] = Field(description="")
    appears_in: List[AppearsIn] = Field(description="")

def load_document(file_path: str):
    converter = DocumentConverter()
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
    preamble = ("\n"
                "Your ability to extract and summarize the relevant 3GPP information accurately is essential for effective research"
                "Pay close attention to the language, structure, and any corss-refrences within the 3GPP data to ensure comprehensive and precise extraction of information."
                "Do not use prior knowledge or information from outside the context to answer the question "
                " Only use the information provided in the context to answer the questions.\n")
    postamble = "Do not include any explanation in the reply. Only include the extracted information in the reply."
    system_template = "{preamble}"
    system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)
    human_template = """{format_instructions}
                        {raw_file_data}
                        Please extract the following data:
                        - Authors: Name, aliases
                        - Documents: doc_id, title, release, type, tags, summary, keywords, etc.
                        - Technology Entities
                        - Working Groups
                        - Meetings
                        - Agendas
                        - Mentions
                        - Authored (Author details)
                        - BelongsTo (Working Group details)
                        - References
                        - AppearsIn (Agenda details)
                        {postamble}
                        """
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    parser = PydanticOutputParser(pydantic_object=DataModel)
    print(parser.get_format_instructions())

    # compile chat template
    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])
    request = chat_prompt.format_prompt(preamble=preamble,
                                        format_instructions=parser.get_format_instructions(),
                                        raw_file_data=raw_file_data,
                                        postamble=postamble).to_messages()
    model = ChatOpenAI()
    print("Querying model...")
    result = model(request, temperature=0)
    print("Response from model:")
    print(result.content)
    return result.content


def process_pdf_files(file_list):
    for file_path in file_list:
        raw_file_data = extract_text(file_path)
        print(f"Extracted text for file {file_path}:\n{raw_file_data}")
        extracted_json = extract_values_from_file(raw_file_data)
        json_file_path = f"{file_path}.json"
        with open(json_file_path, "w") as f:
            f.write(extracted_json)


def main():
    load_dotenv()
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    if len(sys.argv) < 2:
        show_usage_and_exit()

    print(f"Processing path {sys.argv[1]}...")
    file_list = enumerate_pdf_files(sys.argv[1])
    print(f"Processing {len(file_list)} files...")
    print(f"Processing first file: {file_list[0]}...")
    process_pdf_files(file_list)


if __name__ == '__main__':
    main()
    