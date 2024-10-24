from langchain.embeddings import OpenAIEmbeddings
from langchain.llms import AzureOpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from app.database import db

# Initialize OpenAI Embeddings and Chat Model using LangChain
embedding_model = OpenAIEmbeddings(deployment="your-azure-embedding-model", api_key="your-azure-api-key")
chat_model = AzureOpenAI(deployment="your-chat-model", api_key="your-azure-api-key")

def generate_response(user_input):
    # Convert user input into embeddings using Azure OpenAI Embeddings
    user_embedding = embedding_model.embed_query(user_input)

    # Set up a basic prompt template for the chat model
    prompt_template = PromptTemplate(input_variables=["user_input"], template="User: {user_input}\nChatbot:")
    
    # Create a LangChain LLMChain to generate a response
    chain = LLMChain(llm=chat_model, prompt=prompt_template)
    
    # Run the chain with user input
    response = chain.run(user_input=user_input)

    # Optionally store user input and response in PostgreSQL
    # db.session.add(...)
    # db.session.commit()

    return response
