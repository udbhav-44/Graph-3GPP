import getpass
import os

if "OPENAI_API_KEY" not in os.environ:
    os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter your OpenAI API key: ")
    
    
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USERNAME"] = "neo4j"
os.environ["NEO4J_PASSWORD"] = "login123"



from langchain_neo4j import Neo4jGraph

graph = Neo4jGraph()

graph.refresh_schema()
print(graph.schema)

print ("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
enhanced_graph = Neo4jGraph(enhanced_schema=True)
print(enhanced_graph.schema)


from langchain_neo4j import GraphCypherQAChain
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0)
chain = GraphCypherQAChain.from_llm(
    graph=enhanced_graph, llm=llm, verbose=True, allow_dangerous_requests=True
)
response = chain.invoke({"query": "List the documents on CSI enhancement?"})
print(response)