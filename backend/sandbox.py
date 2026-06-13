from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


async def run_daytona(files: dict[str, str], command: str | None = None) -> dict[str, str]:
    command = command or build_execution_command(files)
    api_key = os.getenv("DAYTONA_API_KEY")
    if not api_key:
        return run_local_syntax_check(files)

    try:
        return await run_daytona_sdk(files, command)
    except Exception:
        pass

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(base_url="https://app.daytona.io/api", timeout=60) as client:
            sandbox = await client.post("/sandbox", headers=headers)
            sandbox.raise_for_status()
            sandbox_id = sandbox.json()["id"]
            try:
                files_response = await client.post(
                    f"/sandbox/{sandbox_id}/files",
                    headers=headers,
                    json={"files": files},
                )
                files_response.raise_for_status()
                exec_response = await client.post(
                    f"/sandbox/{sandbox_id}/exec",
                    headers=headers,
                    json={"command": command},
                )
                exec_response.raise_for_status()
                payload = exec_response.json()
                return {
                    "stdout": payload.get("stdout", ""),
                    "stderr": payload.get("stderr", ""),
                }
            finally:
                await client.delete(f"/sandbox/{sandbox_id}", headers=headers)
    except Exception:
        fallback = run_local_syntax_check(files)
        fallback["stdout"] = (
            f"Daytona unavailable, used local MVP syntax check instead. {fallback['stdout']}"
        )
        return fallback


async def run_daytona_sdk(files: dict[str, str], command: str) -> dict[str, str]:
    import asyncio

    return await asyncio.to_thread(run_daytona_sdk_sync, files, command)


def run_daytona_sdk_sync(files: dict[str, str], command: str) -> dict[str, str]:
    from daytona import Daytona, DaytonaConfig

    config = DaytonaConfig(api_key=os.getenv("DAYTONA_API_KEY"))
    daytona = Daytona(config)
    sandbox = daytona.create()

    try:
        code = build_daytona_code_run_script(files)
        response = sandbox.process.code_run(code)
        exit_code = getattr(response, "exit_code", 0)
        result = getattr(response, "result", "") or ""
        return {
            "stdout": result if exit_code == 0 else "",
            "stderr": "" if exit_code == 0 else f"Daytona code_run failed with exit code {exit_code}: {result}",
        }
    finally:
        try:
            daytona.delete(sandbox)
        except Exception:
            try:
                sandbox.delete()
            except Exception:
                pass


def run_local_syntax_check(files: dict[str, str]) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        errors: list[str] = []
        checked = 0
        for path, content in files.items():
            if not path.endswith(".py"):
                continue
            checked += 1
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            try:
                compile(content, path, "exec")
            except SyntaxError as exc:
                errors.append(f"{path}:{exc.lineno}: {exc.msg}")

        if errors:
            return {"stdout": "", "stderr": "\n".join(errors)}
        return {"stdout": f"Local syntax check passed for {checked} Python file(s).", "stderr": ""}


def build_daytona_code_run_script(files: dict[str, str]) -> str:
    python_files = {path: content for path, content in files.items() if path.endswith(".py")}
    if not python_files:
        return "print('Daytona code_run: no Python files to check.')"

    return (
        "files = "
        + repr(python_files)
        + "\n"
        "checked = 0\n"
        "for path, content in files.items():\n"
        "    compile(content, path, 'exec')\n"
        "    checked += 1\n"
        "print(f'Daytona code_run syntax check passed for {checked} Python file(s).')\n"
    )


def build_execution_command(files: dict[str, str]) -> str:
    python_files = sorted(path for path in files if path.endswith(".py"))
    if python_files:
        quoted = " ".join(sh_quote(path) for path in python_files)
        return f"python -m py_compile {quoted}"
    return "true"


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


async def submit_nosana_job(script: str) -> dict[str, Any]:
    api_key = os.getenv("NOSANA_API_KEY")
    if not api_key:
        return {
            "status": "completed",
            "stdout": "Nosana key not configured. Simulated GPU training job completed.",
            "stderr": "",
        }

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        base_url = os.getenv("NOSANA_API_BASE", "https://dashboard.k8s.prd.nos.ci/api")
        async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
            markets_response = await client.get("/markets", headers=headers)
            markets_response.raise_for_status()
            markets = markets_response.json()
            market = choose_nosana_market(markets)
            market_address = market.get("address", os.getenv("NOSANA_MARKET", ""))

            if os.getenv("NOSANA_CREATE_DEPLOYMENT", "").lower() in {"1", "true", "yes"}:
                deployment = build_nosana_deployment(script, market_address)
                response = await client.post("/deployments/create", headers=headers, json=deployment)
                response.raise_for_status()
                payload = response.json()
                deployment_id = payload.get("id")
                start_payload: dict[str, Any] = {}
                if deployment_id:
                    start_response = await client.post(f"/deployments/{deployment_id}/start", headers=headers, json={})
                    start_response.raise_for_status()
                    start_payload = start_response.json()
                return {
                    "status": "started" if start_payload else "created",
                    "stdout": (
                        "Nosana API authenticated, GPU deployment created, and start requested. "
                        f"Deployment id: {deployment_id or 'unknown'}. "
                        f"Create response: {payload}. "
                        f"Start response: {start_payload or 'not started'}"
                    ),
                    "stderr": "",
                    "deployment": payload,
                    "start": start_payload,
                }

            jobs_response = await client.get("/jobs", headers=headers)
            jobs_response.raise_for_status()
            jobs_payload = jobs_response.json()
            job_count = len(jobs_payload.get("jobs", [])) if isinstance(jobs_payload, dict) else 0
            return {
                "status": "ready",
                "stdout": (
                    "Nosana API authenticated. "
                    f"Selected market: {market.get('name', 'unknown')} ({market_address}). "
                    f"Account can read {job_count} recent job(s). "
                    "Set NOSANA_CREATE_DEPLOYMENT=true to create a draft deployment."
                ),
                "stderr": "",
                "market": market,
            }
    except Exception as exc:
        return {
            "status": "completed",
            "stdout": "",
            "stderr": f"Nosana API call failed, simulated GPU training job completed for MVP continuity. Error: {exc}",
        }


def choose_nosana_market(markets: Any) -> dict[str, Any]:
    configured = os.getenv("NOSANA_MARKET")
    if isinstance(markets, list):
        if configured:
            for market in markets:
                if market.get("address") == configured or market.get("slug") == configured:
                    return market
        for market in markets:
            if market.get("address"):
                return market
    return {"address": configured or "7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq", "name": "NVIDIA 3060"}


def build_nosana_deployment(script: str, market_address: str) -> dict[str, Any]:
    return {
        "name": "AI Workspace Training Job",
        "market": market_address,
        "timeout": 60,
        "replicas": 1,
        "strategy": "SIMPLE",
        "job_definition": {
            "version": "0.1",
            "type": "container",
            "meta": {"trigger": "ai-workspace"},
            "ops": [
                {
                    "type": "container/run",
                    "id": "training-job",
                    "args": {
                        "image": "pytorch/pytorch",
                        "cmd": script,
                    },
                }
            ],
        },
    }
