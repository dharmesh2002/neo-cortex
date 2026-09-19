"""
Hybrid orchestrator — decision gate between CrewAI and LangGraph pipelines.

Flow:
  1. CrewAI General Physician (Gemini) assesses the report
  2a. GP resolves it → return CrewAI final report directly
  2b. GP refers to specialist → hand off to LangGraph (NVIDIA Nemotron review)
"""
from .agents.gp_agent import run_gp_assessment
from .graph import healthcare_graph
from .state import MedicalReportState


def run_hybrid_pipeline(initial: MedicalReportState) -> dict:
    """
    Entry point that replaces a direct healthcare_graph.invoke() call.
    Returns a final state dict compatible with app_healthcare.py response shape.
    """
    patient_text = initial.get("patient_report_text", "")
    image_b64 = initial.get("patient_report_b64")
    image_media_type = initial.get("file_media_type", "")

    # ── Stage 1: CrewAI GP Assessment ────────────────────────────────────────
    gp = run_gp_assessment(patient_text, image_b64, image_media_type)

    if gp.get("resolved"):
        # ── Stage 2a: GP resolved — build final state without specialists ────
        return _build_gp_resolved_state(initial, gp)

    # ── Stage 2b: GP referred — hand off to LangGraph specialist pipeline ───
    state: MedicalReportState = {
        **initial,
        "gp_assessment": gp,
        "gp_resolved": False,
        "gp_referral": gp.get("referral", ""),
        "gp_notes": gp.get("referral_reason", ""),
        "pipeline_used": "hybrid",
        "specialists_needed": [],
        "routing_reasoning": "",
        "current_specialist": None,
        "specialist_analyses": [],
        "nvidia_review": None,
        "nvidia_review_success": False,
        "final_report": None,
        "errors": [],
    }

    return healthcare_graph.invoke(state, {"recursion_limit": 30})


def _build_gp_resolved_state(initial: MedicalReportState, gp: dict) -> dict:
    """Construct a final-state dict when the GP resolved the case without referral."""
    urgency_map = {
        "critical": "CRITICAL — Immediate medical attention required",
        "urgent":   "URGENT — Medical review needed within 24–72 hours",
        "routine":  "ROUTINE — Follow up at scheduled appointment",
    }
    urgency_label = urgency_map.get(gp.get("urgency", "routine"), "ROUTINE — Follow up at scheduled appointment")

    report = (
        f"{'═'*50}\n"
        f"NEOCORTEX HEALTHCARE AI — MEDICAL REPORT ANALYSIS\n"
        f"{'═'*50}\n\n"
        f"OVERALL STATUS: {urgency_label}\n\n"
        f"PIPELINE: General Physician (CrewAI + Gemini) — case resolved without specialist referral\n\n"
        f"{'─'*50}\n"
        f"GENERAL PHYSICIAN ASSESSMENT\n"
        f"{'─'*50}\n"
        f"Summary:\n  {gp.get('gp_summary', '')}\n\n"
        f"Confidence: {int(float(gp.get('confidence', 0)) * 100)}%\n\n"
        f"Treatment Plan:\n  {gp.get('treatment', 'No specific treatment noted.')}\n\n"
        f"{'─'*50}\n"
        f"DISCLAIMER: This report is AI-generated and must be reviewed by\n"
        f"licensed medical professionals before clinical decisions are made.\n"
        f"This does not constitute medical advice.\n"
        f"{'─'*50}"
    )

    return {
        **initial,
        "gp_assessment": gp,
        "gp_resolved": True,
        "gp_referral": None,
        "gp_notes": "",
        "pipeline_used": "crewai",
        "specialists_needed": [],
        "routing_reasoning": "GP resolved — no specialist referral needed.",
        "current_specialist": None,
        "specialist_analyses": [],
        "nvidia_review": None,
        "nvidia_review_success": False,
        "final_report": report.strip(),
        "errors": [],
    }
