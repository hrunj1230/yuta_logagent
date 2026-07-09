import os
from fastapi import FastAPI
import src.llm_router as llm
from langgraph.graph import MessagesState, StateGraph, START, END
from langchain_core.messages import HumanMessage

def agent(state: MessagesState) ->dict:
    from langchain_core.messages import AIMessage

    # Codex OAuth는 stream() 메서드를 사용해야 정상 작동
    result_chunks = []
    for chunk in llm.codex_llm.stream(state["messages"]):
        result_chunks.append(chunk)

    # 모든 청크를 합쳐서 최종 메시지 생성
    full_content = "".join([chunk.content for chunk in result_chunks if chunk.content])
    result = AIMessage(content=full_content)
    return {"messages": [result]}

def _graph_builder():
    builder = StateGraph(MessagesState)

    builder.add_node("agent",agent)
    builder.add_edge(START,"agent")
    builder.add_edge("agent",END)

    return builder.compile()

graph = _graph_builder()
def main(req):
    # QueryReq 객체를 MessagesState 형식으로 변환
    input_dict = {
        "messages": [HumanMessage(content=req.req)]
    }
    res = graph.invoke(input_dict)
    # 마지막 메시지의 content 반환
    return res["messages"][-1].content if res.get("messages") else ""



