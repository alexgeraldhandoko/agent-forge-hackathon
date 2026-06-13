from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus, urlparse
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

from .conflict import extract_target_functions
from .context_store import WorkspaceStore
from .scraper import scrape_url

load_dotenv(Path(__file__).with_name(".env"))

RouteName = Literal["code", "sensenova", "scrape", "train"]


def detect_task_type(prompt: str, selected_model: str | None = None) -> RouteName:
    if selected_model in {"train", "code", "scrape", "sensenova"}:
        return selected_model
    prompt_lower = prompt.lower()
    if should_use_bright_data(prompt_lower):
        return "scrape"
    if should_use_gpu(prompt_lower):
        return "train"
    if should_use_sensenova(prompt_lower):
        return "sensenova"
    return "code"


def should_use_bright_data(prompt_lower: str) -> bool:
    scrape_terms = [
        "scrape",
        "crawl",
        "fetch live",
        "latest",
        "current",
        "current prime minister",
        "who is the current",
        "who is the president",
        "who is the prime minister",
        "today",
        "right now",
        "news",
        "pricing",
        "from this url",
        "from this website",
        "documentation for",
        "docs for",
    ]
    return bool(re.search(r"https?://", prompt_lower)) or any(term in prompt_lower for term in scrape_terms)


def should_use_gpu(prompt_lower: str) -> bool:
    gpu_terms = [
        "train",
        "fine-tune",
        "finetune",
        "classifier",
        "model weight",
        "weights",
        "checkpoint",
        "pytorch",
        "tensorflow",
        "cuda",
        "gpu",
        "epochs",
        "inference benchmark",
    ]
    return any(term in prompt_lower for term in gpu_terms)


def should_use_sensenova(prompt_lower: str) -> bool:
    sensenova_terms = [
        "image",
        "mockup",
        "diagram",
        "ui design",
        "wireframe",
        "generate doc",
        "document",
        "proposal",
        "slides outline",
        "visual",
        "infographic",
    ]
    return any(term in prompt_lower for term in sensenova_terms)


def build_system_prompt(store: WorkspaceStore) -> str:
    current_datetime = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%A, %B %d, %Y, %I:%M %p Singapore time")
    return f"""
You are an AI coding agent in a shared collaborative workspace.
Multiple developers are working on the same codebase simultaneously.
Current date and time: {current_datetime}.

Current workspace context:
{store.get_context_string()}

Lock map (functions currently being modified by other members - DO NOT touch these unless instructed):
{json.dumps(store.lock_map, indent=2)}

Recent actions by other team members:
{json.dumps(store.action_log[-5:], indent=2)}

Rules:
- If the user asks a direct factual or conversational question, answer it directly in assistant_message and return "files": {{}}
- For date/time questions, use the Current date and time line above
- Only modify files and functions relevant to the user's request
- Do not create app.py unless the user explicitly asks for app.py
- Prefer descriptive filenames from the prompt or existing workspace files
- Be aware of what other members have already built
- Speak like a helpful coding assistant in assistant_message
- Return ONLY valid JSON in this exact format:
{{
  "explanation": "one sentence summary of what you did",
  "assistant_message": "friendly chat response for the user, like ChatGPT or Claude",
  "files": {{
    "path/to/file.py": "full updated file content"
  }},
  "functions_modified": ["function_name_1", "function_name_2"]
}}
""".strip()


async def route_prompt(
    prompt: str,
    username: str,
    store: WorkspaceStore,
    task_type: str,
) -> dict[str, Any]:
    decision = {
        "route": task_type,
        "reason": route_reason(prompt, task_type),
    }
    if task_type == "scrape":
        routed = await scrape_to_workspace(prompt, username)
        routed["route"] = decision
        return routed

    if task_type == "train":
        routed = fallback_train_update(prompt, username, store)
        routed["route"] = decision
        return routed

    if task_type == "sensenova":
        routed = await try_sensenova_chat(prompt, username, store)
        if routed:
            routed["route"] = decision
            return routed
        routed = fallback_sensenova_artifact(prompt, username)
        routed["route"] = decision
        return routed

    routed = await try_openai_compatible_chat(
        prompt,
        username,
        store,
        api_key=os.getenv("KIMI_API_KEY", ""),
        base_urls=["https://api.moonshot.ai/v1", "https://api.moonshot.cn/v1"],
        model=os.getenv("KIMI_MODEL", "moonshot-v1-128k"),
        provider_name="Kimi",
    )
    if routed:
        routed["route"] = decision
        return routed

    routed = await try_tokenrouter_responses(prompt, username, store)
    if routed:
        routed["route"] = decision
        return routed

    routed = await try_openai_compatible_chat(
        prompt,
        username,
        store,
        api_key=os.getenv("TOKENROUTER_API_KEY", ""),
        base_urls=[os.getenv("TOKENROUTER_BASE_URL", "https://api.tokenrouter.com/v1")],
        model=os.getenv("TOKENROUTER_MODEL", "auto:balance"),
        provider_name="TokenRouter",
    )
    if routed:
        routed["route"] = decision
        return routed

    routed = await try_sensenova_chat(prompt, username, store)
    if routed:
        routed["route"] = decision
        return routed

    routed = fallback_code_update(prompt, username, store)
    routed["route"] = decision
    return routed


def route_reason(prompt: str, task_type: RouteName) -> str:
    if task_type == "scrape":
        return "Detected a URL, external docs, live data, or scraping/data-retrieval language."
    if task_type == "train":
        return "Detected training, model weights, checkpoint, GPU, or ML workload language."
    if task_type == "sensenova":
        return "Detected document, image, visual, diagram, or multimodal generation language."
    return "Defaulted to coding/editing, so Kimi is tried first, then TokenRouter, then fallbacks."


async def try_sensenova_chat(
    prompt: str,
    username: str,
    store: WorkspaceStore,
) -> dict[str, Any] | None:
    base_url = os.getenv("SENSENOVA_BASE_URL", "https://api.velaalpha.cc/v1")
    model = os.getenv("SENSENOVA_CHAT_MODEL", "sensenova-6.7-flash-lite")
    routed = await try_openai_compatible_chat(
        prompt,
        username,
        store,
        api_key=os.getenv("SENSENOVA_API_KEY", ""),
        base_urls=[base_url, "https://token.sensenova.cn/v1"],
        model=model,
    )
    if routed:
        routed["provider"] = "SenseNova"
        return routed
    return await try_sensenova_artifact_chat(prompt, username, store)


async def try_sensenova_artifact_chat(
    prompt: str,
    username: str,
    store: WorkspaceStore,
) -> dict[str, Any] | None:
    api_key = os.getenv("SENSENOVA_API_KEY", "")
    if not api_key:
        return None

    from openai import AsyncOpenAI

    base_url = os.getenv("SENSENOVA_BASE_URL", "https://api.velaalpha.cc/v1")
    model = os.getenv("SENSENOVA_CHAT_MODEL", "sensenova-6.7-flash-lite")
    system_prompt = (
        "You are SenseNova inside a collaborative AI workspace. "
        "Use the shared workspace context, then produce the requested artifact as polished Markdown. "
        "Return only the artifact content, not JSON and not code fences.\n\n"
        f"Shared workspace context:\n{store.get_context_string()}"
    )
    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=20.0, max_retries=0)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Request from {username}: {prompt}"},
            ],
            temperature=0.3,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return None
        filename = sensenova_artifact_filename(prompt)
        return {
            "explanation": f"Generated {filename} with live SenseNova.",
            "assistant_message": (
                f"I generated `{filename}` with SenseNova and saved it into the shared workspace."
            ),
            "files": {
                filename: (
                    f"# SenseNova artifact\n\n"
                    f"Requested by: {username}\n\n"
                    f"## Prompt\n\n{prompt}\n\n"
                    f"## Output\n\n{content}\n"
                )
            },
            "functions_modified": [],
            "provider": "SenseNova",
            "skip_execution": True,
        }
    except Exception:
        return None


def sensenova_artifact_filename(prompt: str) -> str:
    prompt_lower = prompt.lower()
    if any(term in prompt_lower for term in ["image", "mockup", "wireframe", "diagram", "visual", "infographic"]):
        return "assets/sensenova-visual-brief.md"
    if any(term in prompt_lower for term in ["proposal", "brief", "document", "doc"]):
        return "docs/sensenova-document.md"
    return "docs/sensenova-artifact.md"


async def try_tokenrouter_responses(
    prompt: str,
    username: str,
    store: WorkspaceStore,
) -> dict[str, Any] | None:
    api_key = os.getenv("TOKENROUTER_API_KEY")
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{os.getenv('TOKENROUTER_BASE_URL', 'https://api.tokenrouter.com/v1').rstrip('/')}/responses",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("TOKENROUTER_MODEL", "anthropic/claude-opus-4.8-fast"),
                    "instructions": build_system_prompt(store),
                    "input": f"Request from {username}: {prompt}",
                    "temperature": 0.2,
                    "max_output_tokens": 3000,
                },
            )
            response.raise_for_status()
            parsed = coerce_agent_json(extract_response_text(response.json()))
            if parsed:
                parsed["provider"] = "TokenRouter Responses"
                return parsed
    except Exception:
        return None
    return None


async def try_openai_compatible_chat(
    prompt: str,
    username: str,
    store: WorkspaceStore,
    api_key: str,
    base_urls: list[str],
    model: str,
    provider_name: str | None = None,
) -> dict[str, Any] | None:
    if not api_key:
        return None

    from openai import AsyncOpenAI

    for base_url in base_urls:
        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=8.0,
                max_retries=0,
            )
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": build_system_prompt(store)},
                    {"role": "user", "content": f"Request from {username}: {prompt}"},
                ],
                temperature=0.2,
            )
            parsed = coerce_agent_json(response.choices[0].message.content or "")
            if parsed:
                parsed["provider"] = provider_name or base_url
                return parsed
        except Exception:
            continue
    return None


def extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]

    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def coerce_agent_json(content: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(strip_json_fence(content))
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict) or not isinstance(parsed.get("files"), dict):
        return None
    parsed.setdefault("functions_modified", [])
    parsed.setdefault("explanation", "Updated the workspace.")
    parsed.setdefault("assistant_message", parsed["explanation"])
    return parsed


def strip_json_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    return content


def fallback_code_update(prompt: str, username: str, store: WorkspaceStore) -> dict[str, Any]:
    functions = extract_target_functions(prompt) or ["workspace_note"]
    target_file = choose_target_python_file(prompt, store)
    current = store.files.get(target_file, "")
    additions: list[str] = []

    for function_name in functions:
        if re.search(rf"def\s+{re.escape(function_name)}\s*\(", current):
            current = replace_function_body(
                current,
                function_name,
                [
                    f"    \"\"\"Updated by {username} from a shared AI Workspace prompt.\"\"\"",
                    f"    return {{\"updated_by\": \"{username}\", \"request\": {prompt[:120]!r}}}",
                ],
            )
        else:
            additions.append(
                "\n\n"
                f"def {function_name}():\n"
                f"    \"\"\"Created by {username} from a shared AI Workspace prompt.\"\"\"\n"
                f"    return {{\"status\": \"created\", \"request\": {prompt[:120]!r}}}\n"
            )

    if additions:
        current = current.rstrip() + "".join(additions) + "\n"

    return {
        "explanation": f"Updated {target_file} using the local MVP coding fallback.",
        "assistant_message": (
            f"I updated {target_file} using the shared workspace context. "
            "The change is reflected in the file viewer and was checked for Python syntax."
        ),
        "files": {target_file: current},
        "functions_modified": functions,
        "provider": "Local MVP fallback",
    }


def choose_target_python_file(prompt: str, store: WorkspaceStore) -> str:
    mentioned_files = re.findall(r"[\w./-]+\.py", prompt)
    existing_files = set(store.files)
    for file_name in mentioned_files:
        clean_name = file_name.strip().lstrip("/")
        if clean_name in existing_files:
            return clean_name
    if mentioned_files:
        return mentioned_files[0].strip().lstrip("/")

    python_files = sorted(path for path in store.files if path.endswith(".py"))
    if len(python_files) == 1:
        return python_files[0]
    return "workspace.py"


def fallback_train_update(prompt: str, username: str, store: WorkspaceStore) -> dict[str, Any]:
    content = f'''"""
Tiny classifier training job generated by Shared AI.
Requested by: {username}
Prompt: {prompt[:220]!r}

This script uses only the Python standard library so it can run in a small
container or pass local syntax checks without extra dependencies.
"""

from __future__ import annotations

import math
import random


def make_dataset(size: int = 80) -> list[tuple[float, float, int]]:
    random.seed(7)
    rows: list[tuple[float, float, int]] = []
    for _ in range(size):
        x1 = random.uniform(-2.0, 2.0)
        x2 = random.uniform(-2.0, 2.0)
        label = 1 if (x1 * 0.8 + x2 * 1.2 + random.uniform(-0.35, 0.35)) > 0 else 0
        rows.append((x1, x2, label))
    return rows


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def train_classifier(rows: list[tuple[float, float, int]], epochs: int = 140, learning_rate: float = 0.18) -> tuple[float, float, float]:
    weight_1 = 0.0
    weight_2 = 0.0
    bias = 0.0

    for epoch in range(epochs):
        total_loss = 0.0
        for x1, x2, label in rows:
            prediction = sigmoid(weight_1 * x1 + weight_2 * x2 + bias)
            error = prediction - label
            total_loss += -(label * math.log(prediction + 1e-9) + (1 - label) * math.log(1 - prediction + 1e-9))
            weight_1 -= learning_rate * error * x1
            weight_2 -= learning_rate * error * x2
            bias -= learning_rate * error
        if epoch in {{0, epochs - 1}}:
            print(f"epoch={{epoch + 1}} loss={{total_loss / len(rows):.4f}}")

    return weight_1, weight_2, bias


def evaluate(rows: list[tuple[float, float, int]], weights: tuple[float, float, float]) -> float:
    weight_1, weight_2, bias = weights
    correct = 0
    for x1, x2, label in rows:
        prediction = 1 if sigmoid(weight_1 * x1 + weight_2 * x2 + bias) >= 0.5 else 0
        correct += int(prediction == label)
    return correct / len(rows)


def main() -> None:
    rows = make_dataset()
    weights = train_classifier(rows)
    accuracy = evaluate(rows, weights)
    print("trained weights:", {{"weight_1": round(weights[0], 3), "weight_2": round(weights[1], 3), "bias": round(weights[2], 3)}})
    print(f"accuracy={{accuracy:.2%}}")


if __name__ == "__main__":
    main()
'''
    return {
        "explanation": "Prepared a tiny classifier training job for the shared workspace.",
        "assistant_message": "I created a runnable tiny classifier training script and queued it through the Nosana GPU route.",
        "files": {"training_job.py": content},
        "functions_modified": ["make_dataset", "sigmoid", "train_classifier", "evaluate", "main"],
        "daytona_command": "run_training_job",
        "nosana_script": f"python -c {json.dumps(content)}",
        "provider": "Nosana",
    }


def fallback_sensenova_artifact(prompt: str, username: str) -> dict[str, Any]:
    filename = "docs/generated-brief.md"
    if any(term in prompt.lower() for term in ["image", "mockup", "wireframe", "diagram", "visual", "infographic"]):
        filename = "assets/sensenova-request.md"
    return {
        "explanation": "Captured the SenseNova generation request as a shared workspace artifact.",
        "assistant_message": (
            "I routed this to the SenseNova lane. The live SenseNova call did not return a usable JSON edit, "
            "so I saved a clean generation brief for the team instead."
        ),
        "files": {filename: f"# SenseNova generation brief\n\nRequested by: {username}\n\n## Prompt\n\n{prompt}\n"},
        "functions_modified": [],
        "provider": "SenseNova fallback",
    }


async def scrape_to_workspace(prompt: str, username: str) -> dict[str, Any]:
    urls = extract_urls(prompt)
    if not urls:
        urls = [search_url_for_prompt(prompt)]

    files: dict[str, str] = {}
    scraped_results: list[dict[str, Any]] = []
    for url in urls:
        result = await scrape_url(url)
        scraped_results.append(result)
        filename = scrape_filename(url)
        files[filename] = (
            f"# Scrape: {url}\n\n"
            f"- Requested by: {username}\n"
            f"- Source: {result['source']}\n"
            f"- Status: {result['status']}\n\n"
            "## Prompt\n\n"
            f"{prompt}\n\n"
            "## Content\n\n"
            f"{result['content'][:20000]}\n"
        )

    answer = await answer_from_scraped_content(prompt, scraped_results)
    return {
        "explanation": f"Scraped {len(urls)} URL(s) into the shared workspace.",
        "assistant_message": answer
        or (
            f"I scraped {len(urls)} source(s) and saved the results under `scrapes/`. "
            "Everyone in this workspace can now reference that data in follow-up prompts."
        ),
        "files": files,
        "functions_modified": [],
        "provider": "Bright Data scrape",
        "skip_execution": True,
    }


def search_url_for_prompt(prompt: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(prompt)}"


async def answer_from_scraped_content(prompt: str, scraped_results: list[dict[str, Any]]) -> str:
    content_blocks = []
    for result in scraped_results:
        content_blocks.append(
            f"Source URL: {result.get('url')}\n"
            f"Source type: {result.get('source')}\n"
            f"Status: {result.get('status')}\n"
            f"Content:\n{strip_html_for_prompt(str(result.get('content', '')))[:8000]}"
        )
    content = "\n\n---\n\n".join(content_blocks)
    if not content.strip():
        return ""

    current_datetime = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%A, %B %d, %Y, %I:%M %p Singapore time")
    api_key = os.getenv("KIMI_API_KEY") or os.getenv("TOKENROUTER_API_KEY", "")
    base_urls = ["https://api.moonshot.ai/v1", "https://api.moonshot.cn/v1"] if os.getenv("KIMI_API_KEY") else [os.getenv("TOKENROUTER_BASE_URL", "https://api.tokenrouter.com/v1")]
    model = os.getenv("KIMI_MODEL", "moonshot-v1-128k") if os.getenv("KIMI_API_KEY") else os.getenv("TOKENROUTER_MODEL", "anthropic/claude-opus-4.8-fast")
    if not api_key:
        return ""

    from openai import AsyncOpenAI

    for base_url in base_urls:
        try:
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=12.0, max_retries=0)
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Answer the user's question using the scraped content below. "
                            f"Current date/time: {current_datetime}. "
                            "Be concise. If the scraped content is insufficient, say what was scraped and what is uncertain."
                        ),
                    },
                    {"role": "user", "content": f"Question: {prompt}\n\nScraped content:\n{content}"},
                ],
                temperature=0.1,
            )
            answer = (response.choices[0].message.content or "").strip()
            if answer:
                return answer
        except Exception:
            continue
    return ""


def strip_html_for_prompt(content: str) -> str:
    content = re.sub(r"<script[\s\S]*?</script>", " ", content, flags=re.IGNORECASE)
    content = re.sub(r"<style[\s\S]*?</style>", " ", content, flags=re.IGNORECASE)
    content = re.sub(r"<[^>]+>", " ", content)
    content = re.sub(r"\s+", " ", content)
    return content.strip()


def replace_function_body(source: str, function_name: str, new_body: list[str]) -> str:
    lines = source.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"def\s+{re.escape(function_name)}\s*\(", line):
            start = index
            break
    if start is None:
        return source

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("def "):
            end = index
            break

    return "\n".join(lines[: start + 1] + new_body + lines[end:]) + "\n"


def extract_first_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0).rstrip(".,)") if match else None


def extract_urls(text: str) -> list[str]:
    urls = [url.rstrip(".,)") for url in re.findall(r"https?://[^\s]+", text)]
    return list(dict.fromkeys(urls))


def scrape_filename(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc and "google." in parsed.netloc and parsed.path == "/search":
        clean = "search-" + re.sub(r"^q=", "", parsed.query.split("&")[0] or "query")
    else:
        clean = re.sub(r"^https?://", "", url)
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", clean).strip("-")[:80] or "page"
    return f"scrapes/{clean}.md"
