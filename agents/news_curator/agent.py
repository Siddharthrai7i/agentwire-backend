import math
from graph.state import ArticleState
from services.llm import LLMAgentService
from config.settings import app_settings
from services.prompt_manager import prompt_manager
from config.logger import get_logger
from .prompts import NEWS_CURATOR_GENERATION_PROMPT

logger = get_logger(__name__)

def _read_time(text: str) -> str:
    WORDS_PER_MINUTE = 200
    return f"{math.ceil(len(text.split()) / WORDS_PER_MINUTE)} min"

def news_curator_node(state: ArticleState) -> ArticleState:
    logger.info("=> [NewsCuratorAgent] Running...")
    
    # We enforce ainews domain for this agent
    domain = "ainews"
    topic = state.get("topic", "Latest AI News")
    
    tags_config = app_settings.tags.model_dump()
    cat_label = tags_config.get(domain, {}).get("label", domain)
    
    if state.get("dry_run"):
        logger.info("[DRY RUN] Skipping News Research & Generation.")
        return {
            **state,
            "domain": domain,
            "topic": topic,
            "news_data": "Dry run news data.",
            "content": f"# {topic}\n\nDry run AI News text.",
            "read_time": "1 min"
        }

    # --- Step 1: Research (Only run if we haven't already fetched news on this iteration) ---
    news_summary = state.get("news_data", "")
    if not news_summary:
        logger.info("[AGENT] Researching the web for live news...")
        llm_service = LLMAgentService()
        system_prompt = (
            "You are a seasoned AI news researcher. "
            "Use your SearchTools to find the top 3 most important news articles from the past week "
            f"related to the topic: {topic}. "
            "Summarize the findings clearly, providing URL citations. "
            "Be extremely comprehensive as this will be used to write a blog post."
        )
        
        research_agent = llm_service.get_news_agent(system_prompt=system_prompt)
        response = research_agent.invoke({"messages": [("user", f"Find the latest news for {topic}")]})
        news_summary = response["messages"][-1].content
        logger.info(f"[AGENT] Formulated research context ({len(news_summary)} chars).")

    # --- Step 2: Generation ---
    logger.info("[AGENT] Drafting the news blog...")
    validator_feedback = ""
    if state.get("validator_feedback"):
        validator_feedback = f"CRITICAL FEEDBACK FROM PREVIOUS DRAFT. You must fix these issues:\n{state.get('validator_feedback')}"

    prompt = prompt_manager.get_prompt(
        prompt_name="News_Curator_Generation_Prompt",
        fallback_prompt=NEWS_CURATOR_GENERATION_PROMPT,
        cat_label=cat_label,
        topic=topic,
        news_context=news_summary,
        validator_feedback=validator_feedback
    )
    
    llm_service_gen = LLMAgentService(temperature=0.4) # Slightly lower temperature for factual synthesis
    res_gen = llm_service_gen.llm.invoke(prompt)
    
    content = res_gen.content.strip()
    rt = _read_time(content)
    
    logger.info(f"[AGENT] Generated {len(content.split())} words. Read time: {rt}")

    return {
        **state,
        "domain": domain,
        "topic": topic,
        "news_data": news_summary,
        "content": content,
        "read_time": rt
    }
