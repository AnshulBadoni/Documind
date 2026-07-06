"""Routes for chat/Q&A about codebase repositories."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.auth.oauth2 import get_current_user
from src.database import get_db
from src.models.user_model import UserModel
from src.models.project_model import ProjectModel
from src.schemas.chat_schema import ChatRequest, ChatResponse
from src.services.chat_service import ChatService
from src.services.DTO import ResponseDto

router = APIRouter(prefix="", tags=["Codebase Chat"])


def check_daily_question_limit(db: Session, user: UserModel):
    """Enforce daily question limit of 5 for non-whitelisted users."""
    if user.email == "anshulbadoni@gmail.com":
        return

    import datetime
    from src.models.chat_model import ChatMessageModel

    limit_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    questions_today = (
        db.query(ChatMessageModel)
        .filter(
            ChatMessageModel.user_id == user.id,
            ChatMessageModel.role == "user",
            ChatMessageModel.created_at >= limit_time
        )
        .count()
    )
    if questions_today >= 5:
        raise HTTPException(
            status_code=429,
            detail="Daily limit reached. You can only ask 5 questions per day. Upgrade for unlimited access."
        )


@router.post("/projects/{project_id}/chat", response_model=dict)
def chat_about_project(
    project_id: int,
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Ask questions about the project's codebase."""
    # Enforce daily limit
    check_daily_question_limit(db, current_user)

    # Project access validation (owner or shared)
    from src.models.project_share_model import ProjectShareModel
    from sqlalchemy import or_
    project = (
        db.query(ProjectModel)
        .outerjoin(ProjectShareModel, ProjectModel.id == ProjectShareModel.project_id)
        .filter(
            ProjectModel.id == project_id,
            or_(
                ProjectModel.owner_id == current_user.id,
                ProjectShareModel.user_id == current_user.id
            )
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    # 2. Query codebase documents and answer
    chat_svc = ChatService(db)
    try:
        res = chat_svc.chat_about_codebase(
            project_id=project_id,
            message=payload.message,
            user_id=current_user.id,
            session_id=payload.session_id
        )
        return ResponseDto.ok(
            status=200,
            message="Chat response generated successfully",
            data=res
        )
    except Exception as e:
        return ResponseDto.fail(
            status=500,
            message=f"Failed to generate answer: {str(e)}"
        )


from fastapi.responses import StreamingResponse

@router.post("/projects/{project_id}/chat/stream")
def chat_about_project_stream(
    project_id: int,
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
):
    """Ask questions about the project's codebase and receive a streaming event-stream response (SSE)."""
    # Enforce daily limit
    check_daily_question_limit(db, current_user)

    # Project access validation (owner or shared)
    from src.models.project_share_model import ProjectShareModel
    from sqlalchemy import or_
    project = (
        db.query(ProjectModel)
        .outerjoin(ProjectShareModel, ProjectModel.id == ProjectShareModel.project_id)
        .filter(
            ProjectModel.id == project_id,
            or_(
                ProjectModel.owner_id == current_user.id,
                ProjectShareModel.user_id == current_user.id
            )
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    chat_svc = ChatService(db)
    return StreamingResponse(
        chat_svc.chat_about_codebase_stream(
            project_id=project_id,
            message=payload.message,
            user_id=current_user.id,
            session_id=payload.session_id
        ),
        media_type="text/event-stream"
    )


@router.get("/projects/{project_id}/chat/sessions")
def get_chat_sessions(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Retrieve list of distinct chat sessions for a project."""
    from src.models.chat_model import ChatMessageModel
    from sqlalchemy import func
    
    subq = (
        db.query(
            ChatMessageModel.session_id,
            func.min(ChatMessageModel.created_at).label("first_msg_time")
        )
        .filter(
            ChatMessageModel.project_id == project_id,
            ChatMessageModel.user_id == current_user.id
        )
        .group_by(ChatMessageModel.session_id)
        .subquery()
    )
    
    sessions = (
        db.query(ChatMessageModel)
        .join(subq, ChatMessageModel.session_id == subq.c.session_id)
        .filter(
            ChatMessageModel.role == "user",
            ChatMessageModel.project_id == project_id,
            ChatMessageModel.user_id == current_user.id
        )
        .order_by(subq.c.first_msg_time.desc())
        .all()
    )
    
    seen = set()
    res = []
    for s in sessions:
        if s.session_id not in seen:
            seen.add(s.session_id)
            res.append({
                "session_id": s.session_id,
                "title": s.message[:40] + ("..." if len(s.message) > 40 else ""),
                "created_at": s.created_at.isoformat()
            })
            
    return ResponseDto.ok(status=200, message="Sessions retrieved successfully", data=res)


@router.get("/projects/{project_id}/chat/sessions/{session_id}")
def get_chat_session_messages(
    project_id: int,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Retrieve all chat messages in a session."""
    from src.models.chat_model import ChatMessageModel
    
    messages = (
        db.query(ChatMessageModel)
        .filter(
            ChatMessageModel.project_id == project_id,
            ChatMessageModel.user_id == current_user.id,
            ChatMessageModel.session_id == session_id
        )
        .order_by(ChatMessageModel.created_at.asc())
        .all()
    )
    
    res = []
    for m in messages:
        res.append({
            "id": m.id,
            "role": m.role,
            "content": m.message,
            "sources": m.sources.split(",") if m.sources else [],
            "model_name": m.model_name,
            "created_at": m.created_at.isoformat()
        })
        
    return ResponseDto.ok(status=200, message="Messages retrieved successfully", data=res)


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Delete all chat messages in a session (deletes the entire chat session)."""
    from src.models.chat_model import ChatMessageModel
    
    db.query(ChatMessageModel).filter(
        ChatMessageModel.user_id == current_user.id,
        ChatMessageModel.session_id == session_id
    ).delete(synchronize_session=False)
    db.commit()
    return ResponseDto.ok(status=200, message="Chat session deleted successfully")


@router.delete("/chat/messages/{message_id}")
def delete_chat_message(
    message_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Delete a specific chat message from history."""
    from src.models.chat_model import ChatMessageModel
    
    msg = (
        db.query(ChatMessageModel)
        .filter(
            ChatMessageModel.id == message_id,
            ChatMessageModel.user_id == current_user.id
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found or access denied")
        
    db.delete(msg)
    db.commit()
    return ResponseDto.ok(status=200, message="Message deleted successfully")
