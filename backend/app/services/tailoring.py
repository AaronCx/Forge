"""Custom-instructions tailoring — shared by onboarding seeding + run time.

A user's global ``custom_instructions`` are woven into agent prompts both when
agents are seeded (onboarding finish) and at run time (the agent runner +
dispatcher). The block is bounded and clearly delimited, and prepending is
idempotent so a seeded prompt that already carries the block isn't doubled.
"""

ABOUT_USER_MARKER = "--- About this user ---"
END_MARKER = "--- End ---"

# Bounded so the block can't blow up every prompt it's woven into.
MAX_INSTRUCTIONS = 4000


def about_user_block(instructions: str | None) -> str:
    """Return the delimited about-the-user block, or "" when there's nothing."""
    text = (instructions or "").strip()[:MAX_INSTRUCTIONS]
    if not text:
        return ""
    return ABOUT_USER_MARKER + "\n" + text + "\n" + END_MARKER


def prepend_about(system_prompt: str | None, instructions: str | None) -> str:
    """Prepend the about-the-user block to a system prompt (idempotent)."""
    prompt = system_prompt or ""
    if not instructions or ABOUT_USER_MARKER in prompt:
        return prompt
    block = about_user_block(instructions)
    if not block:
        return prompt
    return block + "\n\n" + prompt


def load_custom_instructions(user_id: str | None) -> str:
    """Read a user's stored custom_instructions (empty string when unavailable).

    Read at run time so agents created after onboarding also benefit.
    """
    if not user_id:
        return ""
    try:
        from app.db import get_db

        result = (
            get_db().table("user_preferences")
            .select("custom_instructions")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if result.data:
            return result.data.get("custom_instructions") or ""
    except Exception:
        return ""
    return ""
