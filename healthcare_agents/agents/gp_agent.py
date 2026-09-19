"""
General Physician agent — CrewAI + Gemini.

Assesses the patient report and returns:
  resolved=True  → GP can handle it, no referral needed
  resolved=False → GP refers to a specialist (cardiology / orthopedic)
"""
import json
import os
import re


_GP_SYSTEM = (
    "You are a board-certified General Physician with 25 years of experience. "
    "Your job is to triage patient reports. Determine whether you can manage the "
    "case yourself or whether it requires a specialist referral. "
    "Be conservative — if there is any cardiac or complex musculoskeletal concern, refer."
)

_GP_PROMPT = """Review this patient report and decide: can you resolve it as a GP, or must you refer?

Patient Report:
{report}

Available specialists for referral:
  orthopedic — Bones, joints, spine, fractures, musculoskeletal
  cardiology  — Heart, blood pressure, cholesterol, ECG/EKG, cardiovascular

Respond with ONLY valid JSON (no markdown, no extra text):
{{
  "resolved": false,
  "confidence": 0.85,
  "gp_summary": "One-paragraph summary of your assessment.",
  "treatment": "Treatment plan if resolved, else empty string.",
  "referral": "cardiology",
  "referral_reason": "Why you are referring to this specialist.",
  "urgency": "routine"
}}

Rules:
- resolved: true only if this is clearly a routine GP-manageable case
- referral: EXACT key from the list above (orthopedic | cardiology), empty string if resolved
- urgency: routine | urgent | critical
- confidence: 0.0–1.0
"""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group()
    return json.loads(raw)


def run_gp_assessment(patient_text: str, image_b64: str = None, image_media_type: str = None) -> dict:
    """
    Run the CrewAI General Physician assessment.
    Returns a dict with: resolved, confidence, gp_summary, treatment,
                         referral, referral_reason, urgency
    """
    try:
        from crewai import Agent, Crew, LLM, Task

        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        # LiteLLM expects "gemini/<model>" format
        litellm_model = f"gemini/{gemini_model}"
        api_key = os.environ.get("GOOGLE_API_KEY", "")

        llm = LLM(model=litellm_model, api_key=api_key, temperature=0.1)

        gp = Agent(
            role="General Physician",
            goal="Triage patient reports: resolve or refer to the right specialist.",
            backstory=_GP_SYSTEM,
            llm=llm,
            verbose=False,
            allow_delegation=False,
        )

        task = Task(
            description=_GP_PROMPT.format(report=patient_text[:6000]),
            expected_output="A valid JSON object with keys: resolved, confidence, gp_summary, treatment, referral, referral_reason, urgency.",
            agent=gp,
        )

        crew = Crew(agents=[gp], tasks=[task], verbose=False)
        result = crew.kickoff()

        raw = result.raw if hasattr(result, "raw") else str(result)
        assessment = _parse_json(raw)

        # Validate referral key
        valid_specialists = {"orthopedic", "cardiology"}
        referral = assessment.get("referral", "")
        if referral not in valid_specialists:
            referral = ""
        assessment["referral"] = referral

        # If not resolved but no valid referral, force referral based on content
        if not assessment.get("resolved") and not referral:
            assessment["referral"] = "orthopedic"
            assessment["referral_reason"] = assessment.get("referral_reason", "Defaulting to orthopedic specialist.")

        return assessment

    except Exception as e:
        # Fallback: use direct Gemini call without CrewAI
        return _gp_fallback(patient_text, str(e))


def _gp_fallback(patient_text: str, crewai_error: str) -> dict:
    """Direct Gemini call if CrewAI fails."""
    try:
        from ..llm import call_llm

        raw = call_llm(
            prompt=_GP_PROMPT.format(report=patient_text[:6000]),
            system=_GP_SYSTEM,
        ).strip()
        assessment = _parse_json(raw)
        assessment["_fallback"] = True
        assessment["_crewai_error"] = crewai_error

        valid_specialists = {"orthopedic", "cardiology"}
        if assessment.get("referral", "") not in valid_specialists:
            assessment["referral"] = "" if assessment.get("resolved") else "orthopedic"

        return assessment

    except Exception as e2:
        return {
            "resolved": False,
            "confidence": 0.5,
            "gp_summary": "GP assessment could not be completed. Routing to specialist pipeline.",
            "treatment": "",
            "referral": "orthopedic",
            "referral_reason": f"GP assessment failed ({crewai_error}); defaulting to orthopedic.",
            "urgency": "routine",
            "_fallback": True,
            "_error": str(e2),
        }
