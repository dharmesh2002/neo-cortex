import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class MedicalReportState(TypedDict):
    # Input
    patient_report_text: str
    patient_report_b64: Optional[str]
    file_media_type: Optional[str]
    original_filename: Optional[str]

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
