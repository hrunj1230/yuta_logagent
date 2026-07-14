import os
from fastapi import FastAPI
import src.llm_router as llm
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
import src.tools as tool

tools = [ tool.retriever_vectordb , tool.embedding_file, tool.maker_logfile]

# Claude Sonnet 4.5 사용 - 최고 성능 + 안정적인 tool calling
llm_with_tools = llm.anthropic_llm.bind_tools(tools)
# llm_with_tools = llm.google_llm.bind_tools(tools)  # Gemini 쿼터 초과
# llm_with_tools = llm.codex_llm.bind_tools(tools)  # Codex는 tool calling 문제 있음

SYSTEM_MESSAGE = SystemMessage(content=
"""당신은 개발자 일지 자동 생성 어시스턴트입니다.

작업 순서 (반드시 따르세요):

1️⃣ 데이터 검색
- 사용자가 날짜를 언급하면 retriever_vectordb 도구를 즉시 호출
- date: 날짜 문자열 (예: "2026-07-09")
- reference_len: "5"

2️⃣ 일지 작성
- 검색 결과의 실제 내용을 바탕으로 상세한 일지 작성
- 검색 결과가 비어있으면 "해당 날짜 기록 없음" 명시
- 반드시 검색된 구체적인 내용 포함 (커밋 메시지, 대화 내용, TIL 항목 등)

형식:
# YYYY.MM.DD 일지

## 주요 활동
- [검색 결과에서 추출한 구체적인 작업 내용]

## 학습 내용
- [검색 결과에서 추출한 학습 개념]

## 성과 및 회고
- [검색 결과 기반 회고]

3️⃣ 파일 저장
- 작성한 일지 전체를 maker_logfile 도구로 저장
- date: 날짜 (YYYY-MM-DD)
- content: 위에서 작성한 전체 마크다운

중요: 플레이스홀더 금지! 검색 결과의 실제 내용을 사용하세요.
"""
)

def agent(state: MessagesState) ->dict:
    messages = [SYSTEM_MESSAGE] + state["messages"]

    # invoke 사용 (tool_calls 자동 보존, 모든 LLM 호환)
    result = llm_with_tools.invoke(messages)

    # 디버깅 로그
    print(f"[DEBUG] Agent 응답:")
    print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
    print(f"  - Has tool_calls: {hasattr(result, 'tool_calls') and bool(result.tool_calls)}")
    if hasattr(result, 'tool_calls') and result.tool_calls:
        print(f"  - Tool calls: {result.tool_calls}")

    return {"messages": [result]}
# graph
def _graph_builder():
    builder = StateGraph(MessagesState)
    tool_node = ToolNode(tools=tools)

    builder.add_node("agent",agent)
    builder.add_node("tools",tool_node)
    
    builder.add_edge(START,"agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools":"tools",
            "__end__":END,
        },
    )
    builder.add_edge("tools","agent")

    return builder.compile()
#graph선언
graph = _graph_builder()

def main(req):
    # QueryReq 객체를 MessagesState 형식으로 변환
    input_dict = {
        "messages": [HumanMessage(content=req.req)]
    }
    res = graph.invoke(input_dict)
    # 마지막 메시지의 content 반환
    return res["messages"][-1].content if res.get("messages") else ""



