import json
import re
from datetime import datetime
from graph.state import ArticleState
from services.llm import LLMAgentService
from services.database import DatabaseService
from services.prompt_manager import prompt_manager
from config.logger import get_logger
from .prompts import EDITORIAL_REVIEWER_PROMPT

logger = get_logger(__name__)

def editorial_reviewer_node(state: ArticleState) -> ArticleState:
    logger.info("=> [EditorialReviewerAgent] Running...")
    
    if state.get("dry_run"):
        logger.info("[DRY RUN] Simulating Approval and Metadata Gen.")
        return {
            **state, 
            "revision_needed": False,
            "title": "Dry Run Generated Title",
            "slug": "dry-run-generated",
            "md_path": "db://dry-run",
            "description": "Dry run generic description. For just checking",
        }

    current_revision = state.get("revision_count", 0)
    topic = state.get("topic")
    content = state.get("content", "")
    domain = state.get("domain")
    date = state.get("date", datetime.now().strftime("%Y-%m-%d"))

    prompt = prompt_manager.get_prompt(
        prompt_name="Editorial_Reviewer_Prompt",
        fallback_prompt=EDITORIAL_REVIEWER_PROMPT,
        topic=topic,
        content=content
    )
    
    llm_service = LLMAgentService(temperature=0.1) 
    res = llm_service.llm.invoke(prompt)
    
    raw = res.content.strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE)
    
    try:
        data = json.loads(raw.strip())
        approved = data.get("approved", True)
        feedback = data.get("feedback", "")
        title = data.get("title", topic)
        description = data.get("description", "A blog post about " + topic)
        slug_value = data.get("slug", title.lower().replace(" ", "-"))
    except json.JSONDecodeError:
        logger.warning("[WARN] Editorial reviewer failed to return JSON. Forcing approval fallback.")
        approved = True
        feedback = ""
        title = topic[:70] if topic else "fallback"
        description = "A blog post about " + title
        slug_value = title.lower().replace(" ", "-")
        
    if not approved and current_revision >= 3:
        logger.warning("[WARN] Max revisions reached. Forcing approval.")
        approved = True
        
    revision_needed = not approved
    
    if revision_needed:
        logger.info(f"[AGENT] Draft REJECTED. Feedback: {feedback}")
        return {
            **state,
            "revision_needed": True,
            "validator_feedback": feedback,
            "revision_count": current_revision + 1
        }
        
    logger.info(f"[AGENT] Draft APPROVED! Saving to Database...")
    
    slug_value = re.sub(r"[^\w\s-]", "", slug_value).strip("-")
    
    # Save to Database
    storage = DatabaseService()
    success = storage.save_article(
        domain=domain,
        topic=topic,
        subtopics=state.get("subtopics", ""),
        title=title,
        description=description,
        content=content,
        date=date,
        tags=[domain],
        read_time=state.get("read_time", "5 min"),
        slug=slug_value
    )
    storage.close()
    
    return {
        **state,
        "revision_needed": False,
        "title": title,
        "description": description,
        "slug": slug_value,
        "md_path": f"db://articles/{slug_value}" if success else "failed"
    }
