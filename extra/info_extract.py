import hashlib 
import os
from datetime import datetime
from pydoc import Doc
from typing import List, Optional
from pathlib import Path
# from turtle import title
import sys
from xmlrpc.client import DateTime
from time import time

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
class Contributor(BaseModel):
    '''
    This class represents the contributor of the document
    '''
    name: str = Field(description="")
    aliases: List[str] = Field(description="")

class Document(BaseModel):
    '''
    This class  is used to extract data specific to the document
    '''
    doc_id: str = Field(description="Unique Id of the 3GPP document")
    title: str = Field(description="Title of the document")
    release: str = Field(description="Release the document belongs to ")
    type: Optional[str] = Field(description="The type of document (e.g. specification, report, etc.)")
    tags: Optional[List[str]] = Field(description="Any other specific tags associated with the document")
    summary: str = Field(description="Detailed summary of the entire document in not less than 200 words")
    topic: Optional[str] = Field(description="")
    keywords: List[str] = Field(description="Keywords associated with the document")
    agenda_id: Optional[str] = Field(description="Agenda No. of the document")
    meeting_id: Optional[str] = Field(description="Unique Id of the meeting the document belongs to")
    status: Optional[str] = Field(description="The status of the document (e.g. approved, under review, etc.)")
    working_groups: List[str] = [] # Reference to WorkingGroup 

class TechnologyEntity(BaseModel):
    '''
    This class is used to extract data specific to the technologies or entities mentioned in the document
    '''
    canonical_name: str = Field(description="Name of the technology/entity")
    aliases: List[str] = Field(description="Short-form or other names of the technology/entity")
    description: Optional[str] = Field(description="Explanation of the concept or technology")

class WorkingGroup(BaseModel):
    '''
    This class is used to extract the details of the working group(s) the document belongs to
    '''
    id: str = Field(description="Working group id")
    name: str = Field(description="Name of the working group")
    description: Optional[str] = Field(description=" Description of the working group")

class Meeting(BaseModel):
    '''
    This class is used to extract data of the meeting the document belongs to
    '''
    meeting_id: str = Field(description="Unique Id of the meeting")
    venue: str = Field(description="Venue of the meeting")
    # date: DateTime = Field(description="Date of the meeting")
    wg: str = Field(description="Working group ID")  # Reference to Working Group
    topic: Optional[str] = Field(description="Topic of the meeting")

class Agenda(BaseModel):
    '''
    This class is used to extract data of the agenda the document belongs to
    '''
    agenda_id: str = Field(description="Agenda Number ")
    meeting_id: str = Field(description="Meeting ID of the document where the agenda is discussed")
    topic: Optional[str] = Field(description="Topic of the agenda")
    description: Optional[str] = Field(description="Description of the agenda")

# Edge Models
class Mentions(BaseModel):
    '''
    This class is used to extract the links of technology-entity mentioned in the document
    '''
    doc_id: str = Field(description="Uniquie Id of the document")
    entity_name: str  = Field(description="Name of the technology/entity") # Reference to TechnologyEntity
    context: Optional[str] = Field(description="Context in which the entity is mentioned")
    frequency : Optional[int] = Field(description="How frequently the entity is mentioned in the document")

class Authored(BaseModel):
    '''
    This class is used to extract to the author details of the document
    '''
    doc_id: str = Field(description="Unique Id of the document")
    contributor_name: str = Field(description="Name of the Contributor") # Reference to Author
    contribution_type: Optional[str] = Field(description="Type of the contribution made")

class BelongsTo(BaseModel):
    '''
    This class is used to extract data of the working group the document belongs to
    '''
    doc_id: str = Field(description="Unique Id of the document")
    wg_name: str = Field(description="Working group this document belongs to") # Reference to WorkingGroup
    role_in_group: Optional[str] = Field(description="ROle of the document in the working group") # Role of the document in the working group

class References(BaseModel):
    '''
    This class is used to extract the citation details for the document 
    '''
    # source_doc_id: str = Field(description="Unique ID of the source Document")
    cited_doc_id: str = Field(description="Unique ID of the cited Document")
    type_of_reference: Optional[str]  = Field(description="Type of reference (e.g. Citation, appendix, related work)")# Type of reference (e.g. citation, appendix, related work, etc.)
    details : str = Field(description="Details of the reference in about 20 words") # Details of the reference
class AppearsIn(BaseModel):
    '''
    This class is used to link the agenda to the document
    '''
    agenda_id: str = Field(description="Agenda No of the document")
    page_range: Optional[str] = Field(description="Pages where the specific agenda is discussed")
    doc_id: str = Field(description="Unique Id of the document")

# Main Data Model
class DataModel(BaseModel):
    '''
    This class represents the final data model architecture
    '''
    authors: List[Contributor] = Field(description="Details about the contributors of the document")
    documents: List[Document] = Field(description="Details about the document")
    technology_entities: List[TechnologyEntity] = Field(description="Details of the technologies or entities mentioned in the document")
    working_groups: List[WorkingGroup] = Field(description="Details of the working group(s) the document belongs to")
    meetings: List[Meeting] = Field(description="Details of the meeting the document belongs to")
    agendas: List[Agenda] = Field(description="Details of the agenda the document belongs to")
    mentions: List[Mentions] = Field(description="Links of technology-entity mentioned in the document")
    authored: List[Authored] = Field(description="Links of authors to the document")
    belongs_to: List[BelongsTo] = Field(description="Links of the document/entity to the working group")
    references: List[References] = Field(description="Citation details for the document")
    appears_in: List[AppearsIn] = Field(description="Links of the agenda to the document")

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
    preamble = (
        "\nYour task is to extract structured 3GPP technical information from the document. "
        "Focus on technical specifications, working group relationships, and standard terminology. "
        "Pay special attention to:\n"
        "- Technical terms and their definitions\n"
        "- Relationships between working groups and documents\n"
        "- Document metadata (IDs, types, status)\n"
        "- Cross-references and citations\n"
        "Do not include extraneous commentary.\n"
        "Only output the information structured according to the DataModel.\n"
    )
    
    postamble = "Do not include any explanation in the reply. Only include the extracted information in the reply."
    system_template = "{preamble}"
    system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)
    human_template = """{format_instructions}
                        {raw_file_data}
                        \n
                        {postamble}
                        """
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    parser = PydanticOutputParser(pydantic_object=DataModel)
    # print(parser.get_format_instructions())
    format_instructions = parser.get_format_instructions()
    
    

    # compile chat template
    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])
    request = chat_prompt.format_prompt(preamble=preamble,
                                        format_instructions=parser.get_format_instructions(),
                                        raw_file_data=raw_file_data,
                                        postamble=postamble).to_messages()
    model = ChatOpenAI(model="gpt-4o-mini", temperature=1, model_kwargs={"top_p": 0.4})
    print("Querying model...")
    result = model(request)
    print("Response from model:")
    print(result.content)
    return result.content


def process_pdf_files(file_list):
    for file_path in file_list:
        raw_file_data = extract_text(file_path)
        print(f"Extracted text for file {file_path}:\n{raw_file_data}")
        extracted_json = extract_values_from_file(raw_file_data)
        json_file_path = f"output.json"
        with open(json_file_path, "w") as f:
            f.write(extracted_json)


def main():
    start = time()
    load_dotenv(".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        error_exit("OPENAI_API_KEY environment variable not set")
    os.environ["OPENAI_API_KEY"] = api_key
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