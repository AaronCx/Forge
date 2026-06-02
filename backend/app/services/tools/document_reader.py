from langchain.tools import tool

from app.services.extract import extract_text


@tool
async def document_reader(file_url: str) -> str:
    """Read and extract text from a PDF or DOCX document at the given URL."""
    try:
        return await extract_text(file_url)
    except Exception as e:
        return f"Error reading document: {str(e)}"
