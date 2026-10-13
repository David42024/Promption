"""Extract visible text from typed provider content without stringifying reasoning."""


def final_text(content) -> str:
    """Accept legacy final strings and explicit text blocks; reject unknown shapes."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "".join(
        block["text"] for block in content
        if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
        and isinstance(block.get("text"), str)
        and block.get("thought") is not True
        and block.get("channel", "final") == "final"
    ).strip()
