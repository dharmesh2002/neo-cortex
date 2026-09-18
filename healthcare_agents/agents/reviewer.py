import json
import os
import re

from ..state import MedicalReportState

_REVIEW_PROMPT = """You are a senior medical reviewer. Review the specialist analyses below and respond with ONLY a JSON object — no markdown, no explanation, just the raw JSON.

Specialist Analyses:
{analyses}

Patient Report Summary:
{report}

JSON format (copy this structure exactly):
{{"review_status":"approved","confidence_score":0.90,"agreements":["list what you agree with"],"disagreements":["list what you disagree with, or empty"],"missed_findings":["list missed findings, or empty"],"overall_urgency":"routine","overall_summary":"Your one-paragraph summary for the physician.","reviewed_by":"NVIDIA Nemotron"}}

Use review_status: approved | approved_with_notes | requires_re_evaluation
Use overall_urgency: routine | urgent | critical
"""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    # strip markdown code fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group()
    return json.loads(raw)


def reviewer_node(state: MedicalReportState) -> dict:
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.environ.get("NVIDIA_API_KEY", ""),
        )
        model = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

        # Keep analyses concise to avoid empty responses from token limits
        analyses = state.get("specialist_analyses", [])
        analyses_short = [
            {
                "specialty": a.get("specialty", a.get("specialist_key", "")),
                "severity": a.get("severity", ""),
                "summary": a.get("summary", ""),
                "key_findings": a.get("key_findings", [])[:5],
                "recommendations": a.get("recommendations", [])[:3],
            }
            for a in analyses
        ]

        prompt = _REVIEW_PROMPT.format(
            report=state["patient_report_text"][:2000],
            analyses=json.dumps(analyses_short, indent=2),
        )

        last_err = None
        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a medical reviewer. Reply with only valid JSON, no other text."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024,
                    timeout=60,
                )
                raw = response.choices[0].message.content or ""
                if not raw.strip():
                    raise ValueError("Empty response from NVIDIA model")
                review = _parse_json(raw)
                return {"nvidia_review": review, "nvidia_review_success": True}
            except (json.JSONDecodeError, ValueError) as e:
                last_err = e
                continue  # retry once

        raise last_err or ValueError("NVIDIA review failed after retries")

    except Exception as e:
        msg = f"NVIDIA reviewer unavailable: {type(e).__name__}: {e}"
        return {
            "nvidia_review": {
                "review_status": "unavailable",
                "error": str(e),
                "confidence_score": 0.0,
                "agreements": [],
                "disagreements": [],
                "missed_findings": [],
                "overall_urgency": "routine",
                "overall_summary": "NVIDIA review could not be completed. Please rely on the specialist analyses above.",
                "reviewed_by": "NVIDIA Nemotron (offline)",
            },
            "nvidia_review_success": False,
            "errors": [msg],
        }
