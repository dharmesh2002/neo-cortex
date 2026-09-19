import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class MedicalReportState(TypedDict):
    # Input
    patient_report_text: str
    patient_report_b64: Optional[str]
    file_media_type: Optional[str]
    original_filename: Optional[str]

    # GP assessment (CrewAI stage)
    gp_assessment: Optional[Dict[str, Any]]
    gp_resolved: bool
    gp_referral: Optional[str]   # pre-seeds router when GP refers
    gp_notes: str                # GP reasoning passed to specialists
    pipeline_used: str           # "crewai" | "langgraph" | "hybrid"

    # Router output
    specialists_needed: List[str]
    routing_reasoning: str

    # Set per parallel Send execution
    current_specialist: Optional[str]

    # Accumulated from parallel specialist nodes
    specialist_analyses: Annotated[List[Dict[str, Any]], operator.add]

    # NVIDIA Nemotron review
    nvidia_review: Optional[Dict[str, Any]]
    nvidia_review_success: bool

    # Final assembled report
    final_report: Optional[str]

    # Error log
    errors: Annotated[List[str], operator.add]
