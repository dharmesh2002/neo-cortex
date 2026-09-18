from typing import Annotated, Any, Dict, List, Optional, TypedDict
import operator


class MedicalReportState(TypedDict):
    # Input
    patient_report_text: str
    patient_report_b64: Optional[str]    # base64-encoded image/PDF
    file_media_type: Optional[str]        # e.g. "image/jpeg"
    original_filename: Optional[str]

    # Router output
    specialists_needed: List[str]
    routing_reasoning: str

    # Set per parallel Send execution
    current_specialist: Optional[str]

    # Accumulated from parallel specialist nodes (operator.add = append)
    specialist_analyses: Annotated[List[Dict[str, Any]], operator.add]

    # AWS Bedrock validation
    aws_validation: Optional[Dict[str, Any]]
    aws_validation_success: bool

    # Final assembled report
    final_report: Optional[str]

    # Error log (operator.add = append)
    errors: Annotated[List[str], operator.add]
