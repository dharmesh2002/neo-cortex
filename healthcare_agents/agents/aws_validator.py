import json
import os
import re

from ..state import MedicalReportState

_VALIDATION_PROMPT = """You are a senior medical quality-assurance AI running on AWS Bedrock.
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
  "validated_by": "AWS Bedrock Medical AI Validator"
}}

validation_status: "approved" | "approved_with_notes" | "requires_specialist_review"
overall_urgency:   "routine" | "urgent" | "critical"
confidence_score:  0.0 – 1.0
"""


def aws_validator_node(state: MedicalReportState) -> dict:
    try:
        import boto3

        region = os.getenv("AWS_REGION", "us-east-1")
        model_id = os.getenv(
            "AWS_BEDROCK_MODEL_ID",
            "us.anthropic.claude-sonnet-4-6-20250514-v1:0",
        )

        bedrock = boto3.client(service_name="bedrock-runtime", region_name=region)

        analyses_json = json.dumps(state.get("specialist_analyses", []), indent=2)
        prompt_text = _VALIDATION_PROMPT.format(
            report=state["patient_report_text"][:6000],
            analyses=analyses_json,
        )

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt_text}],
        })

        response = bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        resp_body = json.loads(response["body"].read())
        raw = resp_body["content"][0]["text"].strip()

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group()

        validation = json.loads(raw)
        return {"aws_validation": validation, "aws_validation_success": True}

    except Exception as e:
        msg = f"AWS Bedrock validation unavailable: {type(e).__name__}: {e}"
        return {
            "aws_validation": {
                "validation_status": "unavailable",
                "error": str(e),
                "confidence_score": 0.0,
                "overall_recommendation": (
                    "AWS validation could not be completed. "
                    "Please rely on the specialist analyses above."
                ),
                "validated_by": "AWS Bedrock (offline)",
            },
            "aws_validation_success": False,
            "errors": [msg],
        }
