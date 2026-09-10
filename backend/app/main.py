from dotenv import load_dotenv
load_dotenv()  # Must be first — loads .env before any os.getenv() call

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.database import engine, Base
from app import models

from app.routers import auth, criminals, cases, ai_predictions, admin, gangs, notifications


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables
    Base.metadata.create_all(bind=engine)
    # Auto-seed if empty
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            from seed_data import seed_database
            seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="AI-CRMS API",
    description="Artificial Intelligence Criminal Records Management System",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(criminals.router)
app.include_router(cases.router)
app.include_router(ai_predictions.router)
app.include_router(admin.router)
app.include_router(gangs.router)
app.include_router(notifications.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "AI-CRMS", "version": "1.0.0"}
