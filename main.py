import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# Import database services
from services.database import engine, Base, SessionLocal, Article
from config.logger import get_logger

logger = get_logger(__name__)

# Initialize tables
Base.metadata.create_all(bind=engine)

# Ensure root directory is in sys.path to resolve module imports correctly
ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Load Environment Variables
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ROOT_DIR / ".env")
except ImportError:
    pass

# Initialize Sentry if configured
import sentry_sdk
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=1.0,
        _experiments={
            "continuous_profiling_auto_start": True,
        },
    )

# Import compiled LangGraph instance
from graph.graph import graph

app = FastAPI(
    title="AgentWire API Backend",
    description="REST API service to trigger the autonomous multi-agent blog generator via LangGraph.",
    version="1.0.0"
)

# ── Schemas ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    domain: Optional[str] = Field(
        default=None,
        description="Target domain/category (e.g. 'ml', 'dl', 'nlp', 'cv', 'statistics', 'genai', 'ainews')"
    )
    topic: Optional[str] = Field(
        default=None,
        description="Override topic. If not provided, agents will query history/sourcing APIs to auto-select."
    )
    dry_run: bool = Field(
        default=False,
        description="Dry run mode. Skip actual LLM completions and file storage uploads."
    )
    date: Optional[str] = Field(
        default=None,
        description="Target date in YYYY-MM-DD format (defaults to current date in IST)."
    )

class GenerateResponse(BaseModel):
    message: str
    status: str
    details: dict

# ── Helper ───────────────────────────────────────────────────────────────────

def get_today_ist() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d")

# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Basic health check API."""
    return {
        "status": "healthy",
        "service": "AgentWire-Backend",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/generate", response_model=GenerateResponse, status_code=200)
def generate_blog(request: GenerateRequest):
    """
    Synchronously triggers the multi-agent graph pipeline.
    This will block the response until the validation and compilation completes.
    """
    date_str = request.date or get_today_ist()
    
    initial_state = {
        "date": date_str,
        "dry_run": request.dry_run,
    }
    
    if request.domain:
        initial_state["domain"] = request.domain
    if request.topic:
        initial_state["topic"] = request.topic

    # Configure Thread ID
    thread_id = f"agentwire-sync-{date_str}-{int(datetime.now().timestamp())}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = graph.invoke(initial_state, config=config)
        
        if final_state.get("skipped"):
            return GenerateResponse(
                message="Generation was skipped.",
                status="skipped",
                details={"domain": final_state.get("domain", "?")}
            )

        return GenerateResponse(
            message="Article generated successfully!",
            status="completed",
            details={
                "title": final_state.get("title", "N/A"),
                "domain": final_state.get("domain", "N/A"),
                "read_time": final_state.get("read_time", "N/A"),
                "slug": final_state.get("slug", "N/A"),
                "md_path": final_state.get("md_path", "N/A"),
                "dry_run": request.dry_run
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {str(e)}")

@app.post("/generate/async", status_code=202)
def generate_blog_async(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Triggers the multi-agent graph asynchronously in the background.
    Returns immediately with an 'accepted' status.
    """
    def run_graph_task(state_data: dict, thread_conf: dict):
        try:
            logger.info(f"[Async Queue] Starting generation for target: {state_data}")
            graph.invoke(state_data, config=thread_conf)
            logger.info("[Async Queue] Generation complete.")
        except Exception as err:
            logger.error(f"[Async Queue Error] Execution failed: {err}")

    date_str = request.date or get_today_ist()
    state = {
        "date": date_str,
        "dry_run": request.dry_run,
    }
    
    if request.domain:
        state["domain"] = request.domain
    if request.topic:
        state["topic"] = request.topic

    thread_id = f"agentwire-async-{date_str}-{int(datetime.now().timestamp())}"
    config = {"configurable": {"thread_id": thread_id}}

    background_tasks.add_task(run_graph_task, state, config)
    return {
        "message": "Blog generation task successfully queued in the background.",
        "status": "accepted",
        "thread_id": thread_id
    }


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/articles")
def list_articles(category: Optional[str] = None, db: Session = Depends(get_db)):
    """
    List all articles saved in the database.
    Optionally filter by category/domain (e.g. ?category=ml).
    """
    query = db.query(Article)
    if category:
        query = query.filter(Article.domain == category)
    
    articles = query.order_by(Article.date.desc(), Article.id.desc()).all()
    return [a.to_dict() for a in articles]

@app.get("/articles/{slug}")
def get_article(slug: str, db: Session = Depends(get_db)):
    """
    Retrieve a specific article's full contents and details by slug.
    """
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with slug '{slug}' not found.")
    return article.to_dict()
