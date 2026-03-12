from langchain.tools import tool

from app.providers.registry import provider_registry


@tool
async def data_extractor(text: str) -> str:
    """Extract structured data (JSON) from unstructured text. Identifies entities, dates, amounts, and key-value pairs."""
    response = await provider_registry.complete(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data extraction expert. Extract all structured data from the given text. "
                    "Return a valid JSON object with the following fields where applicable: "
                    "entities (people, organizations, locations), dates, monetary_amounts, key_facts, "
                    "and any other structured data you can identify. Be thorough and precise."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    return response.content or "{}"
