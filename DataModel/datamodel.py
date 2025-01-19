from pydantic import BaseModel, Field
from typing import List, Optional
import json

# Node Models
class Contributor(BaseModel):
    '''
    This class represents the contributor of the document
    '''
    name: str = Field(description="Name of the Organization(Full name) or Individual providing the document")
    aliases: List[str] = Field(description="Any other names or short-forms of the contributor")

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
    canonical_name: str = Field(description="The full, formal name of the technology or entity or concept or theory. This is the primary reference name used in technical or academic contexts. Example: Long Term Evolution (LTE)")
    aliases: List[str] = Field(description="A list of alternative names or abbreviations for the technology/entity, including common aliases, short forms, or informal names. Example: LTE")
    description: Optional[str] = Field(description="A brief explanation or summary of the technology/entity, describing its key characteristics, uses, and significance in the field. This should be clear and concise, providing enough context for someone unfamiliar with the topic. Example: LTE is a standard for wireless broadband communication that offers higher data rates and lower latency than previous technologies.")

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
    
class DataModelEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, DataModel):
            return obj.model_dump()  # Use Pydantic's built-in method
        return super().default(obj)