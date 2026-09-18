import json
import re

from ..llm import call_llm
from ..state import MedicalReportState

SPECIALISTS = {
    "orthopedic": "Bones, joints, spine, fractures, musculoskeletal conditions",
    "cardiology": "Heart, blood pressure, cholesterol, ECG/EKG, cardiovascular conditions",
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
- Default to orthopedic when uncertain
"""


def router_node(state: MedicalReportState) -> dict:
    specialists_str = "\n".join(f"  {k}: {v}" for k, v in SPECIALISTS.items())
    prompt = _ROUTER_PROMPT.format(
        specialists=specialists_str,
        report=state["patient_report_text"][:8000],
    )

    try:
        raw = call_llm(
            prompt=prompt,
            system="You are a medical report triage specialist.",
            image_b64=state.get("patient_report_b64"),
            image_media_type=state.get("file_media_type", ""),
        ).strip()

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group()
        result = json.loads(raw)

        valid = [s for s in result.get("specialists", []) if s in SPECIALISTS]
        if not valid:
            valid = ["orthopedic"]

        return {
            "specialists_needed": valid,
            "routing_reasoning": result.get("reasoning", "Default routing to orthopedic"),
        }

    except Exception as e:
        return {
            "specialists_needed": ["orthopedic"],
            "routing_reasoning": f"Routing failed ({e}) — defaulting to orthopedic",
            "errors": [f"Router error: {e}"],
        }
