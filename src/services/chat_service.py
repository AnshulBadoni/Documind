"""Chat service — handles vector similarity search and question answering using the selected LLM."""

from sqlalchemy.orm import Session
from src.models.code_document_model import CodeDocumentModel
from src.services.llm_service import LLMService


class ChatService:
    """Handles vector search over code documentation and Q&A generation."""

    def __init__(self, db: Session) -> None:
        """Initialise with database session and LLM wrapper."""
        self.db = db
        self.llm = LLMService()

    def chat_about_codebase(self, project_id: int, message: str, user_id: int, session_id: str = "default") -> dict:
        """Query pgvector for relevant code chunks, combine with conversation history, and answer user questions."""
        from src.models.chat_model import ChatMessageModel
        from src.models.user_model import UserModel

        # Get user details for personalized Q&A greeting
        user = self.db.query(UserModel).filter(UserModel.id == user_id).first()
        user_name = user.username if user and user.username else "User"

        # 1. Save user query to DB history
        user_msg = ChatMessageModel(
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            role="user",
            message=message
        )
        self.db.add(user_msg)
        self.db.commit()

        # 2. Retrieve recent chat history context (last 10 messages)
        history = (
            self.db.query(ChatMessageModel)
            .filter(
                ChatMessageModel.project_id == project_id,
                ChatMessageModel.user_id == user_id,
                ChatMessageModel.session_id == session_id
            )
            .order_by(ChatMessageModel.created_at.asc())
            .limit(10)
            .all()
        )

        history_context = ""
        for msg in history[:-1]:  # exclude current query which is already recorded
            history_context += f"{msg.role.upper()}: {msg.message}\n"

        # 3. Generate embedding for user query
        query_vector = self.llm.generate_embedding(message)

        # 4. Perform Cosine Similarity search using pgvector
        matches = (
            self.db.query(CodeDocumentModel)
            .filter(CodeDocumentModel.project_id == project_id)
            .order_by(CodeDocumentModel.embedding.cosine_distance(query_vector))
            .limit(6)
            .all()
        )

        # Supplement with literal keyword matches (LIKE queries) for exact terms
        keyword_matches = []
        words = [w.strip() for w in message.split() if len(w.strip()) > 3]
        if words:
            from sqlalchemy import or_
            likes = [CodeDocumentModel.content.ilike(f"%{word}%") for word in words[:4]]
            keyword_matches = (
                self.db.query(CodeDocumentModel)
                .filter(CodeDocumentModel.project_id == project_id)
                .filter(or_(*likes))
                .limit(4)
                .all()
            )

        # Merge and de-duplicate matches by ID
        all_matches = {m.id: m for m in matches}
        for km in keyword_matches:
            if km.id not in all_matches:
                all_matches[km.id] = km
        
        matches = list(all_matches.values())[:8]

        if not matches:
            return {
                "answer": f"No documentation or code analysis found for this project yet, {user_name}. Please verify if the analysis has completed.",
                "sources": []
            }

        # 5. Construct context
        context_chunks = []
        sources = []
        for match in matches:
            source_info = match.file_path if match.file_path else f"Project Doc: {match.document_type}"
            sources.append(source_info)
            context_chunks.append(f"Source: {source_info}\nContent:\n{match.content}\n---")

        context = "\n".join(context_chunks)

        # 6. Prompt the LLM including context and conversation history
        prompt = (
            f"You are an expert assistant answering questions about a codebase.\n"
            f"Here is the context retrieved from the codebase documentation, API routes, architecture, and file analyses:\n\n"
            f"{context}\n\n"
            f"Conversation History:\n{history_context}\n"
            f"User Question: {message}\n\n"
            f"Answer the user's question accurately using only the context provided. If you do not know or if it is not mentioned, say so."
        )

        system_instruction = (
            f"You are an expert codebase explanation assistant. You are chatting with user '{user_name}'. Your ONLY job is to explain the provided codebase context and answer questions about it.\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. STRICT REFUSAL FOR OFF-TOPIC QUERIES: If the user's question is not directly related to explaining the codebase context provided (e.g., asking to solve a test paper, write generic algorithms, write essays, or chat about unrelated general topics), you MUST refuse to answer and state that you are a codebase explanation tool.\n"
            "2. NO CODE GENERATION/MODIFICATION: You are a codebase explanation and documentation tool, NOT a code generation tool. Even if the user asks for updates, code modifications, refactoring, speed optimizations, or improvements to the codebase (e.g., 'update the AWS connection file for speed', 'write a new function for database connection', 'give me code to fix this file'), you MUST refuse to generate new code or modifications. Instead, explain the current code structure or explain how the change would look theoretically, and explicitly state: 'I am a codebase documentation and explanation tool, not a code generation or modification engine.'\n"
            "Accuracy and adherence to these constraints are absolute."
        )
        answer = self.llm.generate_text(prompt, system_instruction)

        # 7. Save assistant response to DB history
        unique_sources = list(set(sources))
        assistant_msg = ChatMessageModel(
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            message=answer.strip(),
            sources=",".join(unique_sources) if unique_sources else None
        )
        self.db.add(assistant_msg)
        self.db.commit()

        return {
            "answer": answer.strip(),
            "sources": unique_sources
        }

    def chat_about_codebase_stream(self, project_id: int, message: str, user_id: int, session_id: str = "default"):
        """Query pgvector for relevant code chunks, yield chunks dynamically, and Q&A."""
        import json
        from src.models.chat_model import ChatMessageModel
        from src.models.user_model import UserModel

        # Get user details for personalized Q&A greeting
        user = self.db.query(UserModel).filter(UserModel.id == user_id).first()
        user_name = user.username if user and user.username else "User"

        # 1. Save user query to DB history
        user_msg = ChatMessageModel(
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            role="user",
            message=message
        )
        self.db.add(user_msg)
        self.db.commit()

        # 2. Retrieve recent chat history context (last 10 messages)
        history = (
            self.db.query(ChatMessageModel)
            .filter(
                ChatMessageModel.project_id == project_id,
                ChatMessageModel.user_id == user_id,
                ChatMessageModel.session_id == session_id
            )
            .order_by(ChatMessageModel.created_at.asc())
            .limit(10)
            .all()
        )

        history_context = ""
        for msg in history[:-1]:  # exclude current query
            history_context += f"{msg.role.upper()}: {msg.message}\n"

        # 3. Generate embedding and similarity search
        query_vector = self.llm.generate_embedding(message)
        matches = (
            self.db.query(CodeDocumentModel)
            .filter(CodeDocumentModel.project_id == project_id)
            .order_by(CodeDocumentModel.embedding.cosine_distance(query_vector))
            .limit(6)
            .all()
        )

        # Supplement with literal keyword matches (LIKE queries)
        keyword_matches = []
        words = [w.strip() for w in message.split() if len(w.strip()) > 3]
        if words:
            from sqlalchemy import or_
            likes = [CodeDocumentModel.content.ilike(f"%{word}%") for word in words[:4]]
            keyword_matches = (
                self.db.query(CodeDocumentModel)
                .filter(CodeDocumentModel.project_id == project_id)
                .filter(or_(*likes))
                .limit(4)
                .all()
            )

        # Merge and de-duplicate matches by ID
        all_matches = {m.id: m for m in matches}
        for km in keyword_matches:
            if km.id not in all_matches:
                all_matches[km.id] = km
        
        matches = list(all_matches.values())[:8]

        if not matches:
            yield f"data: {json.dumps({'content': f'No documentation or code analysis found for this project yet, {user_name}.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 4. Construct context
        context_chunks = []
        sources = []
        for match in matches:
            source_info = match.file_path if match.file_path else f"Project Doc: {match.document_type}"
            sources.append(source_info)
            context_chunks.append(f"Source: {source_info}\nContent:\n{match.content}\n---")

        context = "\n".join(context_chunks)

        # 5. Prompt the LLM including context and conversation history
        prompt = (
            f"You are an expert assistant answering questions about a codebase.\n"
            f"Here is the context retrieved from the codebase documentation, API routes, architecture, and file analyses:\n\n"
            f"{context}\n\n"
            f"Conversation History:\n{history_context}\n"
            f"User Question: {message}\n\n"
            f"Answer the user's question accurately using only the context provided. If you do not know or if it is not mentioned, say so."
        )

        system_instruction = (
            f"You are an expert codebase explanation assistant. You are chatting with user '{user_name}'. Your ONLY job is to explain the provided codebase context and answer questions about it.\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. STRICT REFUSAL FOR OFF-TOPIC QUERIES: If the user's question is not directly related to explaining the codebase context provided (e.g., asking to solve a test paper, write generic algorithms, write essays, or chat about unrelated general topics), you MUST refuse to answer and state that you are a codebase explanation tool.\n"
            "2. NO CODE GENERATION/MODIFICATION: You are a codebase explanation and documentation tool, NOT a code generation tool. Even if the user asks for updates, code modifications, refactoring, speed optimizations, or improvements to the codebase (e.g., 'update the AWS connection file for speed', 'write a new function for database connection', 'give me code to fix this file'), you MUST refuse to generate new code or modifications. Instead, explain the current code structure or explain how the change would look theoretically, and explicitly state: 'I am a codebase documentation and explanation tool, not a code generation or modification engine.'\n"
            "Accuracy and adherence to these constraints are absolute."
        )

        # 6. Yield sources metadata first
        unique_sources = list(set(sources))
        yield f"data: {json.dumps({'sources': unique_sources})}\n\n"

        # 7. Stream text chunks
        full_response = []
        for chunk in self.llm.generate_text_stream(prompt, system_instruction):
            full_response.append(chunk)
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        # Yield active model name metadata
        yield f"data: {json.dumps({'model_name': self.llm.active_provider})}\n\n"

        # 8. Save assistant response to DB
        assistant_msg = ChatMessageModel(
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            message="".join(full_response).strip(),
            sources=",".join(unique_sources) if unique_sources else None,
            model_name=self.llm.active_provider
        )
        self.db.add(assistant_msg)
        self.db.commit()

        yield "data: [DONE]\n\n"
