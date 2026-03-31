export const API_URL = process.env.NEXT_PUBLIC_API_URL || (() => {
  if (typeof window !== "undefined" && !window.location.hostname.includes("vercel.app")) {
    console.warn("NEXT_PUBLIC_API_URL is not set — falling back to http://localhost:8000. Set this variable for production deployments.");
  }
  return "http://localhost:8000";
})();

export const AVAILABLE_TOOLS = [
  {
    id: "web_search",
    name: "Web Search",
    description: "Search the web for information via SerpAPI",
  },
  {
    id: "document_reader",
    name: "Document Reader",
    description: "Extract text from uploaded PDFs and DOCX files",
  },
  {
    id: "code_executor",
    name: "Code Executor",
    description: "Run Python code in a sandboxed environment",
  },
  {
    id: "data_extractor",
    name: "Data Extractor",
    description: "Extract structured JSON from unstructured text",
  },
  {
    id: "summarizer",
    name: "Summarizer",
    description: "Condense long documents into summaries",
  },
];
