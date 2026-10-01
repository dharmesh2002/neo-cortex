from langgraph.graph import END, START, StateGraph

from .agents import analyze_leads_agent, check_response_agent, email_agent, find_customer_agent
from .state import SalesState


def _after_find(state: SalesState) -> str:
    return "email" if state.get("customer") else END


def _after_email(state: SalesState) -> str:
    return "check_response" if state.get("email_sent") else END


def build_graph():
    g = StateGraph(SalesState)
    g.add_node("find_customer", find_customer_agent)       # Agent 1
    g.add_node("email", email_agent)                       # Agent 2
    g.add_node("check_response", check_response_agent)     # Agent 3
    g.add_node("analyze_leads", analyze_leads_agent)       # Agent 4

    g.add_edge(START, "find_customer")
    g.add_conditional_edges("find_customer", _after_find, ["email", END])
    g.add_conditional_edges("email", _after_email, ["check_response", END])
    g.add_edge("check_response", "analyze_leads")
    g.add_edge("analyze_leads", END)
    return g.compile()


def run(query: str) -> SalesState:
    return build_graph().invoke({"query": query, "log": []})


if __name__ == "__main__":
    import sys
    result = run(sys.argv[1] if len(sys.argv) > 1 else "Priya")
    print("\n".join(result["log"]))
    print(result.get("lead"))
