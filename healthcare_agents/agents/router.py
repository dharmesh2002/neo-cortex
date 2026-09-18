import json
import os
import re

from google import genai
from google.genai import types

from ..state import MedicalReportState

SPECIALISTS = {
    "orthopedic": "Bones, joints, spine, fractures, musculoskeletal conditions",
    "gynecology": "Female reproductive health, pregnancy, menstrual disorders, ovarian/uterine conditions",
    "cardiology": "Heart, blood pressure, cholesterol, ECG/EKG, cardiovascular conditions",
    "neurology": "Brain, nervous system, headache, stroke, seizure, neurological disorders",
    "pulmonology": "Lungs, respiratory, breathing disorders, asthma, COPD, chest X-ray findings",
    "gastroenterology": "Digestive system, liver function, stomach, bowel, GI tract conditions",
    "endocrinology": "Diabetes, thyroid disorders, hormones, insulin, metabolic conditions",
    "general_medicine": "General health assessment, multi-system findings, or unspecified conditions",
}

_ROUTER_PROMPT = """You are a medical report triage specialist. Analyze the patient report and decide which specialist(s) should review it.

Available specialists:
{specialists}

Patient Report:
{report}

Respond with ONLY valid JSON (no markdown, no extra text):
{{
  "specialists": ["key1", "key2"],
  "reasoning": "Brief explanation of the routing decision"
}}

Rules:
- Select 1–3 most relevant specialists using EXACT keys from the list above
- Order by relevance (most relevant first)
- Default to general_medicine when uncertain
"""


def _client():
    return genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))


def _model_name():
    return os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def router_node(state: MedicalReportState) -> dict:
    specialists_str = "\n".join(f"  {k}: {v}" for k, v in SPECIALISTS.items())
    prompt = _ROUTER_PROMPT.format(
        specialists=specialists_str,
        report=state["patient_report_text"][:8000],
    )

    contents = []

    b64 = state.get("patient_report_b64")
    media_type = state.get("file_media_type", "")
    if b64 and media_type.startswith("image/"):
        import base64
        contents.append(types.Part.from_bytes(
            data=base64.b64decode(b64),
            mime_type=media_type,
        ))

    contents.append(prompt)

    try:
        client = _client()
        response = client.models.generate_content(
            model=_model_name(),
            contents=contents,
        )
        raw = response.text.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group()
        result = json.loads(raw)

        valid = [s for s in result.get("specialists", []) if s in SPECIALISTS]
        if not valid:
            valid = ["general_medicine"]

        return {
            "specialists_needed": valid,
            "routing_reasoning": result.get("reasoning", "Default routing to general medicine"),
        }

    except Exception as e:
        return {
            "specialists_needed": ["general_medicine"],
            "routing_reasoning": f"Routing failed ({e}) — defaulting to general medicine",
            "errors": [f"Router error: {e}"],
        }
