from langchain.tools import tool
from PyPDF2 import PdfReader
from docx import Document
import io
import httpx


@tool
async def document_reader(file_url: str) -> str:
    """Read and extract text from a PDF or DOCX document at the given URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(file_url, timeout=30.0)

        if response.status_code != 200:
            return f"Failed to download file: HTTP {response.status_code}"

        content_type = response.headers.get("content-type", "")
        file_bytes = response.content

        if "pdf" in content_type or file_url.lower().endswith(".pdf"):
            return _extract_pdf(file_bytes)
        elif "docx" in content_type or file_url.lower().endswith(".docx"):
            return _extract_docx(file_bytes)
        else:
            # Try to decode as plain text
            return response.text[:10000]

    except Exception as e:
        return f"Error reading document: {str(e)}"


def _extract_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n\n".join(text_parts)[:10000]


def _extract_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(text_parts)[:10000]
