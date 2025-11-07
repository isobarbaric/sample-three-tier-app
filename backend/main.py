from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from db import init_db, get_db, get_all_todos, create_todo as db_create_todo, update_todo as db_update_todo, delete_todo as db_delete_todo


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler - runs on startup and shutdown."""
    # Startup: Initialize database and run migrations
    print("Starting up... Initializing database")
    await init_db()
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(title="Todo App API", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic schemas for API
class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: Optional[int] = 0


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    completed: Optional[bool] = None
    priority: Optional[int] = None


class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    title: str
    description: Optional[str] = None
    completed: bool = False
    created_at: datetime
    priority: int = 0


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to the Todo App API"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/todos", response_model=list[TodoResponse])
async def get_todos(session: AsyncSession = Depends(get_db)):
    """Get all todos from the database."""
    todos = await get_all_todos(session)
    return todos


@app.post("/api/todos", response_model=TodoResponse, status_code=201)
async def create_todo(todo: TodoCreate, session: AsyncSession = Depends(get_db)):
    """Create a new todo in the database."""
    new_todo = await db_create_todo(
        session,
        title=todo.title,
        description=todo.description,
        priority=todo.priority or 0
    )
    return new_todo


@app.put("/api/todos/{todo_id}", response_model=TodoResponse)
async def update_todo(todo_id: int, todo_update: TodoUpdate, session: AsyncSession = Depends(get_db)):
    """Update an existing todo in the database."""
    updated_todo = await db_update_todo(
        session,
        todo_id=todo_id,
        title=todo_update.title,
        description=todo_update.description,
        completed=todo_update.completed,
        priority=todo_update.priority
    )
    
    if updated_todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    
    return updated_todo


@app.delete("/api/todos/{todo_id}", status_code=204)
async def delete_todo(todo_id: int, session: AsyncSession = Depends(get_db)):
    """Delete a todo from the database."""
    success = await db_delete_todo(session, todo_id)
    if not success:
        raise HTTPException(status_code=404, detail="Todo not found")

