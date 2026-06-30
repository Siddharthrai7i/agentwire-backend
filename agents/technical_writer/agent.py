import json
import re
import math
from graph.state import ArticleState
from services.llm import LLMAgentService
from services.database import DatabaseService
from config.settings import app_settings
from services.prompt_manager import prompt_manager
from config.logger import get_logger
from .prompts import TECHNICAL_WRITER_TOPIC_PROMPT, TECHNICAL_WRITER_GENERATION_PROMPT

logger = get_logger(__name__)

def _read_time(text: str) -> str:
    WORDS_PER_MINUTE = 200
    return f"{math.ceil(len(text.split()) / WORDS_PER_MINUTE)} min"

def technical_writer_node(state: ArticleState) -> ArticleState:
    logger.info("=> [TechnicalWriterAgent] Running...")
    
    if state.get("dry_run"):
        logger.info("[DRY RUN] Skipping Database Sourcing and LLM Generation.")
        return {
            **state,
            "domain": state.get("domain") or "ml",
            "topic": state.get("topic") or "Emerging Trends in AI",
            "subtopics": state.get("subtopics") or "Transformers, Attention, GenAI",
            "content": f"# {state.get('topic') or 'Emerging Trends in AI'}\n\nDry run tutorial text.",
            "read_time": "1 min"
        }
    
    storage = DatabaseService()
    
    # --- Step 1: Topic Selection (if not already strictly defined by State) ---
    topic = state.get("topic")
    subtopics = state.get("subtopics", "")
    
    if not topic:
        # Pick domain
        domain_dates = storage.get_all_domains_last_updated()
        # Filter out ainews so technical_writer agent doesn't pick it
        valid_domains = {k: v for k, v in domain_dates.items() if k != "ainews"}
        
        sorted_domains = sorted(valid_domains.items(), key=lambda item: item[1])
        target_domain = sorted_domains[0][0]
        
        tags_config = app_settings.tags.model_dump()
        cat_label = tags_config.get(target_domain, {}).get("label", target_domain)
        
        logger.info(f"[AGENT] Autonomously selected domain: {target_domain}")
        
        recent_history = storage.get_recent_history(target_domain, limit=3)
        history_str = "No recent history found."
        if recent_history:
            history_str = "\n---\n".join([
                f"Title: {item['title']}\nTopic: {item['topic']}\nSubtopics: {item['subtopics']}"
                for item in recent_history
            ])
            
        topic_prompt = prompt_manager.get_prompt("Technical_Writer_Topic_Prompt", TECHNICAL_WRITER_TOPIC_PROMPT, cat_label=cat_label, history=history_str)
        
        llm_service = LLMAgentService(temperature=0.8)
        res = llm_service.llm.invoke(topic_prompt)
        raw = res.content.strip()
        raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE)
        
        try:
            topic_data = json.loads(raw.strip())
            topic = topic_data.get("topic", "Advanced Concepts")
            subtopics = topic_data.get("subtopics", "")
        except json.JSONDecodeError:
            topic = "Emerging Trends in " + cat_label
            subtopics = ""
            
        logger.info(f"[AGENT] Picked Topic: {topic}")
    else:
        target_domain = state.get("domain")
        tags_config = app_settings.tags.model_dump()
        cat_label = tags_config.get(target_domain, {}).get("label", target_domain)
        logger.info(f"[AGENT] Topic already defined: {topic}")

    # --- Step 2: Content Generation ---

    validator_feedback = ""
    if state.get("validator_feedback"):
        validator_feedback = f"CRITICAL FEEDBACK FROM PREVIOUS DRAFT. You must fix these issues:\n{state.get('validator_feedback')}"

    generation_prompt = prompt_manager.get_prompt(
        prompt_name="Technical_Writer_Generation_Prompt",
        fallback_prompt=TECHNICAL_WRITER_GENERATION_PROMPT,
        cat_label=cat_label,
        topic=topic,
        subtopics=subtopics,
        validator_feedback=validator_feedback
    )
    
    llm_service_gen = LLMAgentService(temperature=0.6)
    res_gen = llm_service_gen.llm.invoke(generation_prompt)
    
    content = res_gen.content.strip()
    rt = _read_time(content)
    
    logger.info(f"[AGENT] Generated {len(content.split())} words. Read time: {rt}")

    storage.close()
    return {
        **state,
        "domain": target_domain,
        "topic": topic,
        "subtopics": subtopics,
        "content": content,
        "read_time": rt
    }
