import json

from app.brightdata import WebResearchContext
from app.models import AgentSession, RunSessionRequest, WorkspaceState


KIMI_SYSTEM_PROMPT = """You are KimiAI inside a collaborative AI coding workspace.
You help implement code changes while respecting shared locks and active teammates.
Use the provided workspace context. Be concise, specific, and implementation-focused.
When web_research is provided, treat it as the source of truth for current web information and cite URLs from it.
If you cannot safely infer a change, say what information is missing."""


def build_model_messages(
    session: AgentSession,
    state: WorkspaceState,
    request: RunSessionRequest,
    web_research: WebResearchContext | None = None,
) -> list[dict[str, str]]:
    context = {
        "workspace": state.workspace.model_dump(mode="json"),
        "current_session": session.model_dump(mode="json"),
        "active_locks": [lock.model_dump(mode="json") for lock in state.locks],
        "recent_events": [event.model_dump(mode="json") for event in state.events[-20:]],
        "web_research": web_research.model_dump(mode="json") if web_research else None,
    }

    user_content = {
        "member_prompt": session.prompt,
        "task_type": session.task_type.value,
        "targets": [target.model_dump(mode="json") for target in session.targets],
        "extra_instructions": request.instructions,
        "workspace_context": context,
    }

    return [
        {"role": "system", "content": KIMI_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_content, indent=2)},
    ]


build_kimi_messages = build_model_messages
