import json
import re

from ..llm import call_llm
from ..state import MedicalReportState

SPECIALIST_CONFIGS = {
    "orthopedic": {
        "name": "Orthopedic Specialist",
        "system": (
            "You are a board-certified Orthopedic Surgeon with 20+ years of experience. "
            "You specialise in bones, joints, cartilage, ligaments, tendons, muscles, and spine. "
            "Analyze medical reports, X-ray/MRI descriptions, and lab findings that relate to the "
            "musculoskeletal system. Provide precise, evidence-based clinical assessments."
        ),
    },
    "cardiology": {
        "name": "Cardiology Specialist",
        "system": (
            "You are a board-certified Interventional Cardiologist with 20+ years of experience. "
            "You specialise in ECG/EKG interpretation, echocardiograms, lipid panels, blood pressure, "
            "cardiac biomarkers, and cardiovascular risk assessment. "
            "Provide precise, evidence-based clinical assessments."
        ),
    },
}

_ANALYSIS_PROMPT = """Analyze this patient's medical report from your {specialty_name} perspective.

Patient Report:
{report}

Return ONLY valid JSON (no markdown, no preamble):
{{
  "specialty": "{specialty_name}",
  "key_findings": ["Specific finding 1", "Specific finding 2"],
  "normal_values": ["Lab/measurement within normal range"],
  "abnormal_values": ["Lab/measurement outside normal range — include the value"],
  "concerns": ["Clinical concern or red flag"],
  "recommendations": ["Specific actionable recommendation"],
  "severity": "routine",
  "follow_up_required": true,
  "follow_up_timeframe": "within 2 weeks",
  "summary": "One-paragraph summary of findings from the {specialty_name} perspective"
}}

For "severity" use EXACTLY one of:
  "routine"  — can be addressed at a scheduled appointment
  "urgent"   — should be seen within 24–72 hours
  "critical" — requires immediate attention / emergency care
"""


def run_specialist(state: MedicalReportState) -> dict:
    specialist_key = state.get("current_specialist") or "orthopedic"
    config = SPECIALIST_CONFIGS.get(specialist_key, SPECIALIST_CONFIGS["orthopedic"])

    prompt = _ANALYSIS_PROMPT.format(
        specialty_name=config["name"],
        report=state["patient_report_text"][:12000],
    )

    try:
        raw = call_llm(
            prompt=prompt,
            system=config["system"],
            image_b64=state.get("patient_report_b64"),
            image_media_type=state.get("file_media_type", ""),
        ).strip()

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group()
        analysis = json.loads(raw)
        analysis["specialist_key"] = specialist_key

        return {"specialist_analyses": [analysis]}

    except Exception as e:
        return {
            "specialist_analyses": [{
                "specialist_key": specialist_key,
                "specialty": config["name"],
                "severity": "routine",
                "key_findings": ["Analysis could not be completed"],
                "normal_values": [],
                "abnormal_values": [],
                "concerns": ["Manual specialist review required"],
                "recommendations": ["Please consult a licensed specialist"],
                "follow_up_required": True,
                "follow_up_timeframe": "as soon as possible",
                "summary": f"Automated analysis failed: {e}",
            }],
            "errors": [f"Specialist '{specialist_key}' error: {e}"],
        }
