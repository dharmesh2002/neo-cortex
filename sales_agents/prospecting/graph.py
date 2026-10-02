from langgraph.graph import END, START, StateGraph

from .agents import decision_maker_agent, discover_agent, website_contact_agent, export_node, profile_agent, rank_agent
from .state import ProspectState


def build_graph():
    g = StateGraph(ProspectState)
    g.add_node("profile", profile_agent)
    g.add_node("discover", discover_agent)
    g.add_node("decision_makers", decision_maker_agent)
    g.add_node("website_contacts", website_contact_agent)
    g.add_node("rank", rank_agent)
    g.add_node("export", export_node)
    g.add_edge(START, "profile")
    g.add_edge("profile", "discover")
    g.add_edge("discover", "decision_makers")
    g.add_edge("decision_makers", "website_contacts")
    g.add_edge("website_contacts", "rank")
    g.add_edge("rank", "export")
    g.add_edge("export", END)
    return g.compile()


def run(sectors=None, regions=None) -> ProspectState:
    return build_graph().invoke({"sectors": sectors or [], "regions": regions or [], "log": []})


if __name__ == "__main__":
    out = run()
    print("\n".join(out["log"]))
    for c in out["companies"][:10]:
        print(c["score"], c["name"], "-", c["sector"], c["city"])
