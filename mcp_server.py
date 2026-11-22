import sys
from pathlib import Path
from typing import Annotated

from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from app import search

server = MCPServer(
    name="study-notes",
    version="1.0.0",
    instructions="Search and quiz from the user's AI engineering study notes.",
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
def notes_search(
    query: Annotated[str, Field(min_length=1, max_length=500, description="What to look for, in plain English")],
    top_k: Annotated[int, Field(ge=1, le=10, description="How many passages to return, 1 to 10")] = 3,
) -> str:
    """Search the user's AI engineering study notes by meaning and return the most relevant passages with similarity scores.
    Use when the user asks about something they studied: prompting, structured outputs, tool use, context engineering, embeddings, RAG, evals, or MCP.
    Do not use for general questions unrelated to their notes, or to list topics (use notes_list_sections)."""
    results = search.search(query, top_k)
    return "\n\n".join(f"[{i}] (score {score:.2f}) {chunk}" for i, (score, chunk) in enumerate(results, start=1))


@server.tool(annotations=READ_ONLY)
def notes_list_sections() -> str:
    """List the section headings in the user's study notes, one per line.
    Use to see which topics the notes cover before searching.
    Do not use to answer questions about a topic (use notes_search)."""
    lines = search.NOTES_PATH.read_text().splitlines()
    return "\n".join(line.lstrip("# ").strip() for line in lines if line.startswith("## "))


@server.resource("notes://all", name="all_notes", description="The full text of the user's study notes.", mime_type="text/markdown")
def all_notes() -> str:
    return search.NOTES_PATH.read_text()


@server.prompt(description="Quiz the user on a topic from their study notes.")
def quiz_me(topic: str) -> str:
    return (
        f"Use the notes_search tool to find what my notes say about {topic}. "
        "Then ask me 5 short-answer questions about it, one at a time. "
        "Wait for my answer before the next question, and correct me using the notes."
    )


if __name__ == "__main__":
    server.run()
