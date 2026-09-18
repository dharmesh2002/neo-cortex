from langgraph.graph import END, START, StateGraph

try:
    from langgraph.types import Send
except ImportError:
    from langgraph.constants import Send  # type: ignore[no-redef]

from .agents.reviewer import reviewer_node
from .agents.router import router_node
from .agents.specialists import run_specialist
from .state import MedicalReportState


def assemble_final_report(state: MedicalReportState) -> dict:
    analyses = state.get("specialist_analyses", [])
    review = state.get("nvidia_review") or {}

    severities = [a.get("severity", "routine").lower() for a in analyses]
    if "critical" in severities:
        overall = "CRITICAL — Immediate medical attention required"
    elif "urgent" in severities:
        overall = "URGENT — Medical review needed within 24–72 hours"
    else:
        overall = "ROUTINE — Follow up at scheduled appointment"

    specialist_sections = []
    for a in analyses:
        name = a.get("specialty") or a.get("specialist_key", "Unknown").replace("_", " ").title()
        sev = a.get("severity", "routine").upper()
        findings = "\n".join(f"  • {f}" for f in a.get("key_findings", []))
        abnormal = "\n".join(f"  • {f}" for f in a.get("abnormal_values", []))
        recs = "\n".join(f"  • {r}" for r in a.get("recommendations", []))
        fu = ""
        if a.get("follow_up_required"):
            fu = f"\n  Follow-up: {a.get('follow_up_timeframe', 'as directed')}"

        specialist_sections.append(
            f"{'─'*50}\n"
            f"SPECIALIST: {name}  |  Severity: {sev}\n"
            f"{'─'*50}\n"
            f"Summary:\n  {a.get('summary', 'No summary provided.')}\n\n"
            f"Key Findings:\n{findings or '  None noted'}\n\n"
            f"Abnormal Values:\n{abnormal or '  None noted'}\n\n"
            f"Recommendations:\n{recs or '  None'}{fu}"
        )

    review_section = ""
    if review and review.get("review_status") != "unavailable":
        review_section = (
            f"\n{'═'*50}\n"
            f"NVIDIA NEMOTRON — INDEPENDENT REVIEW\n"
            f"{'═'*50}\n"
            f"Status:      {review.get('review_status', 'N/A')}\n"
            f"Confidence:  {int(float(review.get('confidence_score', 0)) * 100)}%\n"
            f"Urgency:     {review.get('overall_urgency', 'N/A').upper()}\n\n"
            f"Summary:\n  {review.get('overall_summary', 'N/A')}\n"
        )
        if review.get("disagreements"):
            review_section += "\nDisagreements with Gemini:\n" + "\n".join(f"  ⚠ {d}" for d in review["disagreements"])
        if review.get("missed_findings"):
            review_section += "\nMissed Findings:\n" + "\n".join(f"  → {m}" for m in review["missed_findings"])
        if review.get("agreements"):
            review_section += "\nAgreements:\n" + "\n".join(f"  ✓ {a}" for a in review["agreements"])

    specialists_consulted = ", ".join(
        (a.get("specialty") or a.get("specialist_key", "")).replace("_", " ").title()
        for a in analyses
    )

    report = (
        f"{'═'*50}\n"
        f"NEOCORTEX HEALTHCARE AI — MEDICAL REPORT ANALYSIS\n"
        f"{'═'*50}\n\n"
        f"OVERALL STATUS: {overall}\n\n"
        f"Specialists Consulted: {specialists_consulted}\n"
        f"Routing Reasoning: {state.get('routing_reasoning', 'N/A')}\n\n"
        + "\n\n".join(specialist_sections)
        + review_section
        + "\n\n"
        f"{'─'*50}\n"
        f"DISCLAIMER: This report is AI-generated and must be reviewed by\n"
        f"licensed medical professionals before clinical decisions are made.\n"
        f"This does not constitute medical advice.\n"
        f"{'─'*50}"
    )

    return {"final_report": report.strip()}


def route_to_specialists(state: MedicalReportState):
    specialists = state.get("specialists_needed") or ["general_medicine"]
    return [Send("run_specialist", {**state, "current_specialist": s}) for s in specialists]


def build_healthcare_graph():
    g = StateGraph(MedicalReportState)

    g.add_node("router", router_node)
    g.add_node("run_specialist", run_specialist)
    g.add_node("nvidia_reviewer", reviewer_node)
    g.add_node("assemble_report", assemble_final_report)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", route_to_specialists, ["run_specialist"])
    g.add_edge("run_specialist", "nvidia_reviewer")
    g.add_edge("nvidia_reviewer", "assemble_report")
    g.add_edge("assemble_report", END)

    return g.compile()


healthcare_graph = build_healthcare_graph()
