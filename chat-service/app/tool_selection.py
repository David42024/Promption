"""Per-request least-privilege tool exposure for Promption Shop.

Resource reads are pre-fetched with their server ACL and passed as untrusted data.
Do not offer the model an unrelated resource tool merely because the session role
could use it for *another* request. MCP enforces authorization again at execution.
"""

from __future__ import annotations


INTERACTIVE = frozenset({"ask_user", "make_document", "attach_existing_document"})


def tools_for_request(specs: list[dict], *, policy_tools=(), fetched=(),
                      file_requested=False, has_documents=False, capabilities_question=False,
                      web_requested=False, public_only=True, allow_interactive=True) -> list[dict]:
    """Select candidate tools without granting any new capability or role."""
    if capabilities_question:
        return []
    allow_reads = set(policy_tools) - set(fetched)
    # A pre-fetched, authorized resource is normally sufficient to answer or
    # explain what is missing. Avoid calling a dialogue tool just to ask again.
    allowed = allow_reads | ({"ask_user"} if allow_interactive else set())
    if web_requested and public_only:
        allowed.update({"web_search", "web_open"})
    if file_requested:
        allowed.add("make_document")
        if has_documents:
            allowed.add("attach_existing_document")
    return [s for s in specs if isinstance(s, dict) and
            isinstance(s.get("function"), dict) and
            s["function"].get("name") in allowed]
