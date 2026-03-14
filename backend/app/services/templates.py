"""Pre-built agent templates seeded on startup."""

TEMPLATES = [
    {
        "name": "Document Analyzer",
        "description": "Upload a PDF or DOCX and get a structured summary with key entities, dates, and action items.",
        "system_prompt": (
            "You are a document analysis expert. When given a document's text content, you must:\n"
            "1. Identify the document type and purpose\n"
            "2. Extract all key entities (people, organizations, locations)\n"
            "3. List all dates, deadlines, and monetary amounts\n"
            "4. Summarize the main points\n"
            "5. Identify any action items or next steps\n\n"
            "Format your output with clear headers and bullet points."
        ),
        "tools": ["document_reader", "data_extractor", "summarizer"],
        "workflow_steps": [
            "Read and extract text from the uploaded document",
            "Extract structured data including entities, dates, and amounts",
            "Generate a comprehensive summary with key findings and action items",
        ],
        "is_template": True,
    },
    {
        "name": "Research Agent",
        "description": "Give a topic and the agent searches the web, synthesizes findings, and generates a structured report.",
        "system_prompt": (
            "You are a thorough research analyst. When given a topic:\n"
            "1. Search for the most relevant and recent information\n"
            "2. Cross-reference multiple sources\n"
            "3. Synthesize findings into a coherent narrative\n"
            "4. Highlight key statistics and facts\n"
            "5. Present a balanced view with multiple perspectives\n\n"
            "Always cite your sources and indicate confidence levels."
        ),
        "tools": ["web_search", "summarizer"],
        "workflow_steps": [
            "Search the web for comprehensive information on the topic",
            "Analyze and cross-reference the search results",
            "Synthesize findings into a structured research report with citations",
        ],
        "is_template": True,
    },
    {
        "name": "Data Extractor",
        "description": "Paste unstructured text and extract structured data as clean JSON or CSV format.",
        "system_prompt": (
            "You are a data extraction specialist. Your job is to:\n"
            "1. Analyze the provided unstructured text\n"
            "2. Identify all structured data within it\n"
            "3. Extract entities, relationships, and key-value pairs\n"
            "4. Output clean, well-formatted JSON\n\n"
            "Be thorough — extract every piece of structured data you can find. "
            "Use consistent naming conventions in your output."
        ),
        "tools": ["data_extractor"],
        "workflow_steps": [
            "Analyze the input text to identify all structured data patterns",
            "Extract all entities, dates, amounts, and relationships as structured JSON",
        ],
        "is_template": True,
    },
    {
        "name": "Code Reviewer",
        "description": "Paste code for automated review covering bugs, security issues, performance, and best practices.",
        "system_prompt": (
            "You are a senior software engineer conducting a thorough code review. Analyze the provided code for:\n"
            "1. **Bugs**: Logic errors, off-by-one errors, null/undefined handling\n"
            "2. **Security**: SQL injection, XSS, hardcoded secrets, input validation\n"
            "3. **Performance**: N+1 queries, unnecessary allocations, algorithmic complexity\n"
            "4. **Best Practices**: Naming conventions, code organization, error handling\n"
            "5. **Suggestions**: Concrete improvements with code examples\n\n"
            "Rate severity as: Critical, Warning, or Info. Be specific — reference line numbers."
        ),
        "tools": ["code_executor"],
        "workflow_steps": [
            "Analyze the code for bugs, security vulnerabilities, and logic errors",
            "Review for performance issues and best practice violations",
            "Generate a structured review report with severity ratings and improvement suggestions",
        ],
        "is_template": True,
    },
]


async def seed_templates(supabase_client):
    """Seed template agents if they don't exist yet."""
    existing = supabase_client.table("agents").select("name").eq("is_template", True).execute()
    existing_names = {r["name"] for r in (existing.data or [])}

    for template in TEMPLATES:
        if template["name"] not in existing_names:
            # Use a system-level user_id; look up the first existing user to satisfy FK
            first_user = supabase_client.table("agents").select("user_id").limit(1).execute()
            system_uid = first_user.data[0]["user_id"] if first_user.data else "00000000-0000-0000-0000-000000000000"
            template["user_id"] = system_uid
            supabase_client.table("agents").insert(template).execute()
