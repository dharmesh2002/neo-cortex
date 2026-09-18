import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

load_dotenv()

app = FastAPI(title="NeoCortex Healthcare AI", version="1.0.0")
_executor = ThreadPoolExecutor(max_workers=4)
_html = Path(__file__).parent / "templates" / "healthcare.html"


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(_html)


@app.post("/api/analyze")
async def analyze_report(
    report_file: Optional[UploadFile] = File(None),
    report_text: Optional[str] = Form(None),
):
    from healthcare_agents import healthcare_graph
    from healthcare_agents.state import MedicalReportState
    from healthcare_agents.utils import (
        extract_text_from_pdf,
        file_to_base64,
        get_file_media_type,
        is_image,
        is_pdf,
    )

    initial: MedicalReportState = {
        "patient_report_text": "",
        "patient_report_b64": None,
        "file_media_type": None,
        "original_filename": None,
        "specialists_needed": [],
        "routing_reasoning": "",
        "current_specialist": None,
        "specialist_analyses": [],
        "aws_validation": None,
        "aws_validation_success": False,
        "final_report": None,
        "errors": [],
    }

    if report_file and report_file.filename:
        file_bytes = await report_file.read()
        media_type = get_file_media_type(report_file.filename)
        initial["original_filename"] = report_file.filename
        initial["file_media_type"] = media_type

        if is_pdf(media_type):
            initial["patient_report_text"] = extract_text_from_pdf(file_bytes)
        elif is_image(media_type):
            initial["patient_report_b64"] = file_to_base64(file_bytes)
            initial["patient_report_text"] = (
                f"[Image report: {report_file.filename}. "
                "The image is being analyzed directly by vision-capable specialists.]"
            )
        else:
            initial["patient_report_text"] = file_bytes.decode("utf-8", errors="replace")

    elif report_text and report_text.strip():
        initial["patient_report_text"] = report_text.strip()
    else:
        raise HTTPException(status_code=400, detail="Please provide a report file or paste report text.")

    if not initial["patient_report_text"] and not initial.get("patient_report_b64"):
        raise HTTPException(status_code=400, detail="Could not extract content from the uploaded report.")

    loop = asyncio.get_event_loop()
    try:
        final_state = await loop.run_in_executor(
            _executor,
            lambda: healthcare_graph.invoke(initial, {"recursion_limit": 30}),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    return JSONResponse({
        "success": True,
        "routing": {
            "specialists": final_state.get("specialists_needed", []),
            "reasoning": final_state.get("routing_reasoning", ""),
        },
        "specialist_analyses": final_state.get("specialist_analyses", []),
        "aws_validation": final_state.get("aws_validation"),
        "aws_validation_success": final_state.get("aws_validation_success", False),
        "final_report": final_state.get("final_report", ""),
        "errors": final_state.get("errors", []),
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
