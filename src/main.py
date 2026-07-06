"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.database import init_db
from src.routes.analysis_run_routes import router as analysis_run_router
from src.routes.auth_routes import router as auth_router
from src.routes.chat_routes import router as chat_router
from src.routes.entry_routes import router as entry_router
from src.routes.exclusion_routes import router as exclusion_router
from src.routes.oauth_routes import router as oauth_router
from src.routes.project_routes import router as project_router

app = FastAPI(
    title="FastAPI Backend",
    description="Production-ready FastAPI backend with clean layered architecture",
    version="1.0.0",
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(project_router)
app.include_router(chat_router)
app.include_router(entry_router)
app.include_router(exclusion_router)
app.include_router(analysis_run_router)


@app.on_event("startup")
def startup() -> None:
    """Initialise the database on application startup."""
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    """Health-check endpoint."""
    return {"status": "ok", "message": "API is running"}
