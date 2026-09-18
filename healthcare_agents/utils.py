import base64
import io


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except ImportError:
        return "[PDF text extraction unavailable — install pypdf]"
    except Exception as e:
        return f"[PDF text extraction failed: {e}]"


def file_to_base64(file_bytes: bytes) -> str:
    return base64.standard_b64encode(file_bytes).decode("utf-8")


def get_file_media_type(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "pdf": "application/pdf",
        "txt": "text/plain",
    }.get(ext, "application/octet-stream")


def is_image(media_type: str) -> bool:
    return media_type.startswith("image/")


def is_pdf(media_type: str) -> bool:
    return media_type == "application/pdf"
