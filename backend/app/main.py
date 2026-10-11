import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api.health import router as health_router
from app.api.analyze import router as analyze_router
from app.api.tutor import router as tutor_router
from app.api.visualize import router as visualize_router
from app.api.quiz import router as quiz_router

# Load environment variables
load_dotenv()

app = FastAPI(
    title="AI CodeMentor API",
    description="Backend API for AI CodeMentor - an interactive code explanation and learning platform",
    version="0.1.0",
)

# Configure CORS origins
raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(health_router)
app.include_router(analyze_router)
app.include_router(tutor_router)
app.include_router(visualize_router)
app.include_router(quiz_router)



@app.get("/", tags=["Root"])
def root():
    """Root info endpoint."""
    return {
        "name": "AI CodeMentor API",
        "version": "0.1.0",
        "health_check": "/api/health",
        "docs_url": "/docs",
    }
