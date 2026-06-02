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
