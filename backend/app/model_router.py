from app.models import ModelRoute, TaskType


def route_model(task_type: TaskType, prompt: str) -> ModelRoute:
    """Route requests to the provider that best matches the task type."""
    normalized_prompt = prompt.lower()

    if task_type == TaskType.ml or "train" in normalized_prompt:
        return ModelRoute(
            provider="Nosana",
            model="gpu-job",
            reason="GPU-backed route for model training or heavy ML workloads.",
        )

    if task_type == TaskType.image or "image" in normalized_prompt:
        return ModelRoute(
            provider="SenseNova",
            model="sensenova-u1",
            reason="Multimodal route for image or document generation tasks.",
        )

    if task_type == TaskType.web or "scrape" in normalized_prompt or "latest docs" in normalized_prompt:
        return ModelRoute(
            provider="Bright Data + KimiAI",
            model="web-context-coding",
            reason="Live web context is gathered before passing the task to the coding model.",
        )

    if task_type == TaskType.coding:
        return ModelRoute(
            provider="KimiAI",
            model="kimi-k2.6",
            reason="Primary coding route with workspace context and lock awareness.",
        )

    return ModelRoute(
        provider="KimiAI",
        model="kimi-general",
        reason="Default route for general workspace reasoning.",
    )

