from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from graph.state import ArticleState

from agents.technical_writer.agent import technical_writer_node
from agents.news_curator.agent import news_curator_node
from agents.editorial_reviewer.agent import editorial_reviewer_node


def _route_start(state: ArticleState) -> str:
    """Decides which Generation Track to take based on requested domain."""
    if state.get("skipped"):
        return END

    if state.get("domain") == "ainews":
        return "news_curator"
    return "technical_writer"

def _route_after_reviewer(state: ArticleState) -> str:
    """Supervisor logic handling the Revision loop."""
    if state.get("revision_needed"):
        # Route back to the specific generator if rejected
        if state.get("domain") == "ainews":
            return "news_curator"
        return "technical_writer"
    
    # If approved by Editorial Reviewer, the graph perfectly concludes.
    return END

def build_graph() -> StateGraph:
    builder = StateGraph(ArticleState)

    # 1. Add all agents
    builder.add_node("technical_writer", technical_writer_node)
    builder.add_node("news_curator", news_curator_node)
    builder.add_node("editorial_reviewer", editorial_reviewer_node)

    # 2. Wire the execution edges
    builder.add_conditional_edges(
        START, 
        _route_start, 
        {
            END: END,
            "news_curator": "news_curator",
            "technical_writer": "technical_writer"
        }
    )
    
    # Both generator agents funnel down universally to the editorial reviewer agent
    builder.add_edge("technical_writer", "editorial_reviewer")
    builder.add_edge("news_curator", "editorial_reviewer")
    
    # Editorial Reviewer enforces standards, looping back if corrections are demanded
    builder.add_conditional_edges(
        "editorial_reviewer",
        _route_after_reviewer,
        {
            "technical_writer": "technical_writer",
            "news_curator": "news_curator",
            END: END
        }
    )

    return builder.compile(checkpointer=InMemorySaver())

# Expose compiled graph instance
graph = build_graph()
