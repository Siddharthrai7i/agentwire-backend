from typing import Optional, List
from langchain_groq import ChatGroq
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from config.settings import app_settings
from config.logger import get_logger
from tools import TavilySearchTool, GuardianSearchTool

logger = get_logger(__name__)


class LLMAgentService:
    """
    A core service class responsible for managing LLM connections and 
    orchestrating tool-binding for multi-agent workflows.
    
    This class adheres to OOP principles, allowing easy instantiation 
    of different base LLMs and assembling specialized agents as needed.
    """
    
    def __init__(self, model_name: Optional[str] = None, temperature: Optional[float] = None):
        """
        Initializes the LLM Service with specific model configurations.
        
        Args:
            model_name (Optional[str]): The Groq model variant to use. Defaults to settings.
            temperature (Optional[float]): The inference temperature. Defaults to settings.
        """
        self.model_name = model_name or app_settings.GROQ_MODEL_NAME
        self.temperature = temperature if temperature is not None else app_settings.GROQ_TEMPERATURE
        self.api_key = app_settings.GROQ_API_KEY
        
        # Statically instantiate the main LLM client for reuse across agents created by this service
        self.llm = self._initialize_llm()

    def _initialize_llm(self) -> ChatGroq:
        """
        Core logic to instantiate the connection with Groq.
        
        Returns:
             ChatGroq: An active, authenticated Groq LLM instance.
        """
        return ChatGroq(
            model=self.model_name,
            temperature=self.temperature,
            api_key=self.api_key
        )
        
    def get_news_agent(self, system_prompt: Optional[str] = None):
        """
        Constructs a specialized News Research Agent equipped with our web-search tools.
        
        Args:
            system_prompt (Optional[str]): Context or behavioral instructions injected into the StateGraph.
            
        Returns:
            CompiledGraph: A runnable LangGraph ReAct agent pre-equipped with Tavily and Guardian search tools.
        """
        # Step 1: Initialize the tools designed for the News Agent
        news_tools: List[BaseTool] = [
            TavilySearchTool(),
            GuardianSearchTool()
        ]
        
        # Step 2: Bind the tools and LLM using LangGraph's prebuilt ReAct orchestrator
        agent = create_react_agent(
            model=self.llm,
            tools=news_tools,
            prompt=system_prompt
        )
        return agent

