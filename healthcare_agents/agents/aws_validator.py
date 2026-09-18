import json
import os
import re

from google import genai
from google.genai import types

from ..state import MedicalReportState

_VALIDATION_PROMPT = """You are a senior medical quality-assurance AI.
Your role: cross-validate the specialist analyses below for consistency, completeness, and clinical accuracy.

Original Patient Report:
{report}

Specialist Analyses:
{analyses}

Return ONLY valid JSON (no markdown):
{{
  "validation_status": "approved",
  "confidence_score": 0.92,
  "cross_specialist_findings": [
    "Consistent finding observed across specialists",
    "Complementary finding that strengthens the clinical picture"
  ],
  "conflicts_identified": [
    "Conflicting interpretation between two specialists — describe the conflict"
  ],
  "missed_considerations": [
    "Clinically important finding not addressed by any specialist"
  ],
  "drug_interaction_flags": [
    "Potential medication concern (if any medications are mentioned)"
  ],
  "overall_urgency": "routine",
  "overall_recommendation": "Consolidated recommendation for the treating physician",
  "validated_by": "Gemini Medical AI Validator"
}}

validation_status: "approved" | "approved_with_notes" | "requires_specialist_review"
overall_urgency:   "routine" | "urgent" | "critical"
confidence_score:  0.0 – 1.0
"""


def _client():
    return genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))


def _model_name():
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def aws_validator_node(state: MedicalReportState) -> dict:
    try:
        analyses_json = json.dumps(state.get("specialist_analyses", []), indent=2)
        prompt_text = _VALIDATION_PROMPT.format(
            report=state["patient_report_text"][:6000],
            analyses=analyses_json,
        )

        client = _client()
        response = client.models.generate_content(
            model=_model_name(),
            contents=prompt_text,
            config=types.GenerateContentConfig(
                system_instruction="You are a senior medical quality-assurance AI validator.",
            ),
        )
        raw = response.text.strip()

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group()

        validation = json.loads(raw)
        return {"aws_validation": validation, "aws_validation_success": True}

    except Exception as e:
        msg = f"Validation unavailable: {type(e).__name__}: {e}"
        return {
            "aws_validation": {
                "validation_status": "unavailable",
                "error": str(e),
                "confidence_score": 0.0,
                "overall_recommendation": (
                    "AI validation could not be completed. "
                    "Please rely on the specialist analyses above."
                ),
                "validated_by": "Gemini Validator (offline)",
            },
            "aws_validation_success": False,
            "errors": [msg],
        }
