import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-3.7-flash", temperature=0)

client = MultiServerMCPClient({
    "postgres": {
        "command": sys.executable,
        "args": [str(Path(__file__).parent / "mcp_server.py")],
        "transport": "stdio",
    }
})

LOG_FILE = Path("agent_log.jsonl")
system = SystemMessage(content="""You are a PostgreSQL Q&A assistant.
You MUST use tools to answer questions. Do not guess.
Step 1: call list_tables to see what tables exist.
Step 2: call get_schema to check columns.
Step 3: call run_query to get data.
Answer concisely with the actual data.""")


async def ask(question: str) -> str:
    tools = await client.get_tools()
    llm_with_tools = llm.bind_tools(tools)

    def call_model(state):
        return {"messages": [llm_with_tools.invoke([system] + state["messages"])]}

    def should_continue(state):
        last = state["messages"][-1]
        if last.tool_calls:
            return "tools"
        return END

    def extract_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(block.get("text", "") for block in content if isinstance(block, dict))
        return str(content)

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue)
    builder.add_edge("tools", "agent")
    graph = builder.compile()

    log_entry = {"timestamp": datetime.now().isoformat(), "question": question}
    final_answer = None


    async for step in graph.astream({"messages": [HumanMessage(content=question)]}):
        for node, state in step.items():
            if node == "tools":
                for msg in state["messages"]:
                    if hasattr(msg, "tool_calls"):
                        log_entry["tool_calls"] = [
                            {"name": tc["name"], "args": tc["args"]}
                            for tc in msg.tool_calls
                        ]
            if node == "agent":
                final_answer = extract_text(state["messages"][-1].content)

    log_entry["answer"] = final_answer
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return final_answer


async def main():
    print("postgres-qa agent. type 'exit' to quit.\n")
    while True:
        try:
            q = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("exit", "quit"):
            break
        answer = await ask(q)
        print(f"\nagent: {answer}\n")


if __name__ == "__main__":
    asyncio.run(main())