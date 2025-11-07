"""Database utilities and migration management."""
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
from models import Base, Todo

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Database URL - defaults to SQLite for local development
# Infrastructure layer should override this with environment variable
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./todos.db")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db():
    """Get database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database and run migrations."""
    async with engine.begin() as conn:
        # Create all tables from SQLAlchemy models
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables created/verified")
        
        # Run SQL migrations for additional setup (indexes, etc.)
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        
        for migration_file in migration_files:
            version = migration_file.stem
            
            # Check if migration already applied
            result = await conn.execute(
                text("SELECT version FROM schema_migrations WHERE version = :version"),
                {"version": version}
            )
            row = result.fetchone()
            
            if row is None:
                print(f"Applying migration: {version}")
                
                # Read and execute migration
                with open(migration_file, 'r') as f:
                    migration_sql = f.read()
                
                # Execute each statement separately
                for statement in migration_sql.split(';'):
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        # Skip CREATE TABLE statements - already handled by models
                        if not statement.upper().startswith('CREATE TABLE'):
                            await conn.execute(text(statement))
                
                # Record migration as applied
                await conn.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": version}
                )
                
                print(f"✓ Migration {version} applied successfully")
            else:
                print(f"Migration {version} already applied, skipping")
        
        print("Database initialized successfully!")


async def get_all_todos(session: AsyncSession):
    """Get all todos from database."""
    result = await session.execute(
        select(Todo).order_by(Todo.created_at.desc())
    )
    return result.scalars().all()


async def get_todo_by_id(session: AsyncSession, todo_id: int):
    """Get a single todo by ID."""
    result = await session.execute(
        select(Todo).where(Todo.id == todo_id)
    )
    return result.scalar_one_or_none()


async def create_todo(session: AsyncSession, title: str, description: str = None, priority: int = 0):
    """Create a new todo."""
    todo = Todo(
        title=title,
        description=description,
        completed=False,
        priority=priority
    )
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return todo


async def update_todo(session: AsyncSession, todo_id: int, title: str = None, description: str = None, completed: bool = None, priority: int = None):
    """Update an existing todo."""
    todo = await get_todo_by_id(session, todo_id)
    
    if todo is None:
        return None
    
    # Update fields if provided
    if title is not None:
        todo.title = title
    if description is not None:
        todo.description = description
    if completed is not None:
        todo.completed = completed
    if priority is not None:
        todo.priority = priority
    
    await session.commit()
    await session.refresh(todo)
    return todo


async def delete_todo(session: AsyncSession, todo_id: int):
    """Delete a todo."""
    todo = await get_todo_by_id(session, todo_id)
    
    if todo is None:
        return False
    
    await session.delete(todo)
    await session.commit()
    return True
