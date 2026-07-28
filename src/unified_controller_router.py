"""
Unified Source Management Agent (Router Approach)

This module provides a router-based multi-agent system with separate
source management and embedding execution sub-agents. The router analyzes
user requests and delegates to the appropriate specialized agent.

Public API:
    unified_agent(user_id: str, message: str) -> str
"""

from typing import Annotated, Literal, TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from . import llm_router
from .tools import source as source_tools
from .tools import embedding as embedding_tools


# Checkpointer for conversation history
checkpointer = InMemorySaver()


# Extended state with routing information
class UnifiedState(TypedDict):
    """State for router agent with routing destination field"""
    messages: Annotated[list, add_messages]
    route_destination: str


# Pydantic model for router decision
class RouteDecision(BaseModel):
    """Router agent decision output"""
    destination: Literal["source_management", "embedding_execution"] = Field(
        description="'source_management' for CRUD operations or 'embedding_execution' for embedding tasks"
    )
    reasoning: str = Field(
        description="Explanation for this routing choice"
    )
