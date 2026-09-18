import json
import re

import anthropic

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
    "gynecology": {
        "name": "Gynecology & Obstetrics Specialist",
        "system": (
            "You are a board-certified Gynecologist/Obstetrician with 20+ years of experience. "
            "You specialise in female reproductive health, pregnancy, menstrual disorders, PCOS, "
            "endometriosis, hormonal conditions, and related lab/imaging findings. "
            "Provide precise, evidence-based clinical assessments."
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
    "neurology": {
        "name": "Neurology Specialist",
        "system": (
            "You are a board-certified Neurologist with 20+ years of experience. "
            "You specialise in MRI/CT brain and spine findings, EEG interpretation, CSF analysis, "
            "neurological exam findings, and neuro-relevant lab markers. "
            "Provide precise, evidence-based clinical assessments."
        ),
    },
    "pulmonology": {
        "name": "Pulmonology Specialist",
        "system": (
            "You are a board-certified Pulmonologist with 20+ years of experience. "
            "You specialise in chest X-ray and CT chest findings, spirometry/PFT results, ABG, "
            "SpO2 trends, and respiratory-related lab markers. "
            "Provide precise, evidence-based clinical assessments."
        ),
    },
    "gastroenterology": {
        "name": "Gastroenterology Specialist",
        "system": (
            "You are a board-certified Gastroenterologist with 20+ years of experience. "
            "You specialise in liver function tests, colonoscopy/endoscopy reports, stool analysis, "
            "abdominal imaging findings, and GI-related lab markers. "
            "Provide precise, evidence-based clinical assessments."
        ),
    },
    "endocrinology": {
        "name": "Endocrinology Specialist",
        "system": (
            "You are a board-certified Endocrinologist with 20+ years of experience. "
            "You specialise in blood glucose, HbA1c, thyroid function (TSH/T3/T4), cortisol, "
            "hormonal panels, and metabolic markers. "
            "Provide precise, evidence-based clinical assessments."
        ),
    },
    "general_medicine": {
        "name": "General Medicine Specialist",
        "system": (
            "You are a board-certified Internist/General Physician with 20+ years of experience. "
            "You provide comprehensive general health assessments covering CBC, metabolic panels, "
            "vital signs, and overall health status, identifying conditions that need specialist referrals. "
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
    specialist_key = state.get("current_specialist") or "general_medicine"
    config = SPECIALIST_CONFIGS.get(specialist_key, SPECIALIST_CONFIGS["general_medicine"])
    client = anthropic.Anthropic()

    user_content = []

    # Forward image to vision-capable analysis
    b64 = state.get("patient_report_b64")
    media_type = state.get("file_media_type", "")
    if b64 and media_type.startswith("image/"):
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })

    user_content.append({
        "type": "text",
        "text": _ANALYSIS_PROMPT.format(
            specialty_name=config["name"],
            report=state["patient_report_text"][:12000],
        ),
    })

    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=4096,
            system=config["system"],
            messages=[{"role": "user", "content": user_content}],
        )

        raw = response.content[0].text.strip()
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
