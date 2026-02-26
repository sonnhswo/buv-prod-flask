from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from openai import BadRequestError

from app.database import AzureAISearchRetriever, QnARetriever
from app.utils import language_detection_chain, add_prefix_to_answer
from app.chains import create_conversational_rag_chain, create_relevant_questions_chain, conversational_chain
from config import Config

config = Config()

# Managing chat history
store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()

    return store[session_id]

def trim_message_history(session_id: str):
    if session_id in store:
        store[session_id].messages = store[session_id].messages[-10:] if len(store[session_id].messages) > 10 else store[session_id].messages

def clear_history(session_id: str):
    if session_id in store:
        del store[session_id]

def generate_response(user_input: str, session_id: str, chatbot_id: str, chatbot_name: str) -> dict:
    try:
        language_detection = language_detection_chain.invoke({"input": user_input})
        if language_detection.language != "English":
            answer = "We're sorry for any inconvenience; however, our chatbot can only answer questions in English. Thank you for your understanding!"
            source = None
            page_number = None
            relevant_questions = []
        else:
            # create history aware retriever
            qna_retriever = QnARetriever(chatbot=chatbot_id, chatbot_name=chatbot_name, k=1)
            doc_retriever = AzureAISearchRetriever(chatbot=chatbot_id, chatbot_name=chatbot_name, k=config.DOC_TOP_K)
            question_retriever = AzureAISearchRetriever(chatbot=chatbot_id, chatbot_name=chatbot_name, k=config.QUESTION_TOP_K)

            conversational_rag_chain = create_conversational_rag_chain(doc_retriever, get_session_history)
            relevant_questions_chain = create_relevant_questions_chain(question_retriever)
            
            trim_message_history(session_id)

            qna_found = qna_retriever.invoke(user_input)

            # QnA found - return found answer + relevant questions
            if len(qna_found):
                questions_found = relevant_questions_chain.invoke(qna_found[0].page_content)

                answer = qna_found[0].page_content
                source = qna_found[0].metadata.get("title")
                page_number = qna_found[0].metadata.get("page_number")
                relevant_questions = questions_found.questions
            
            # QnA not found - proceed with normal workflow
            else:
                output = conversational_chain(conversational_rag_chain, relevant_questions_chain, user_input, session_id)
                
                answer = output.get("answer")
                source = output.get("source")
                page_number = output.get("page_number")
                relevant_questions = output.get("relevant_questions")

        return {
            "answer": add_prefix_to_answer(answer, chatbot_name),
            "source": source,
            "page_number": page_number,
            "relevant_questions": relevant_questions
        }
    
    except (BadRequestError, ValueError) as e:
        print(e)
        standard_message = "For further assistance, please contact our Student Information Office via email at studentservice@buv.edu.vn or by phone at 0936 376 136."
        
        return {
            "answer": add_prefix_to_answer(standard_message, chatbot_name),
            "source": None,
            "page_number": None,
            "relevant_questions": []
        }
    except Exception as e:
        print(e)


def generate_response_stream(user_input: str, session_id: str, chatbot_id: str, uni_name: str):
    """Generator function for streaming responses"""
    try:
        language_detection = language_detection_chain.invoke({"input": user_input})
        print(f"{language_detection=}")
        
        if language_detection.language != "English":
            answer = "We're sorry for any inconvenience; however, our chatbot can only answer questions in English. Thank you for your understanding!"
            yield {'type': 'content', 'content': answer}
            yield {'type': 'metadata', 'source': None, 'page_number': None}
            yield {'type': 'questions', 'relevant_questions': []}
            yield {'type': 'done'}
        else:
            # Initialize retrievers
            qna_retriever = QnARetriever(chatbot=chatbot_id, chatbot_name=uni_name, k=1)
            question_retriever = AzureAISearchRetriever(chatbot=chatbot_id, chatbot_name=uni_name, k=config.QUESTION_TOP_K)
            
            relevant_questions_chain = create_relevant_questions_chain(question_retriever)

            print(f"Before trimming {store=}")
            trim_message_history(session_id)
            print(f"After trimming {store=}")
            
            # 1. Check for QnA exact match first
            qna_found = qna_retriever.invoke(user_input)
            
            if len(qna_found):
                # QnA found - stream the pre-defined answer
                questions_found = relevant_questions_chain.invoke(qna_found[0].page_content)
                answer = add_prefix_to_answer(qna_found[0].page_content, uni_name)
                
                # Stream the answer word by word to match UI expectations
                words = answer.split(' ')
                for i, word in enumerate(words):
                    if i == 0:
                        yield {'type': 'content', 'content': word}
                    else:
                        yield {'type': 'content', 'content': ' ' + word}
                
                # Yield metadata, questions, and done signal
                yield {'type': 'metadata', 'source': qna_found[0].metadata.get("title"), 'page_number': qna_found[0].metadata.get("page_number")}
                yield {'type': 'questions', 'relevant_questions': questions_found.questions}
                yield {'type': 'done'}
                
            # 2. QnA not found - proceed with standard RAG stream
            else:
                doc_retriever = AzureAISearchRetriever(chatbot=chatbot_id, chatbot_name=uni_name, k=config.DOC_TOP_K)
                conversational_rag_chain = create_conversational_rag_chain(doc_retriever, get_session_history)
                
                from app.chains import conversational_chain_stream
                for chunk in conversational_chain_stream(conversational_rag_chain, relevant_questions_chain, user_input, session_id, uni_name):
                    yield chunk
                
    except (BadRequestError, ValueError) as e:
        print(e)
        standard_message = "For further assistance, please contact our Student Information Office via email at studentservice@buv.edu.vn or by phone at 0936 376 136."
        yield {'type': 'content', 'content': add_prefix_to_answer(standard_message, uni_name)}
        yield {'type': 'metadata', 'source': None, 'page_number': None}
        yield {'type': 'questions', 'relevant_questions': []}
        yield {'type': 'done'}
    except Exception as e:
        print(e)
        yield {'type': 'error', 'error': str(e)}
