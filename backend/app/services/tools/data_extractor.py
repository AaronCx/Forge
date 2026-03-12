import os

from langchain.tools import tool
from openai import AsyncOpenAI


@tool
async def data_extractor(text: str) -> str:
    """Extract structured data (JSON) from unstructured text. Identifies entities, dates, amounts, and key-value pairs."""
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
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
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or "{}"
