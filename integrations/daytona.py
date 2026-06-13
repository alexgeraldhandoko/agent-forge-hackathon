"""
Daytona sandbox — isolated code execution via the multi-step API.
Flow: POST /sandbox → POST /sandbox/{id}/files → POST /sandbox/{id}/exec → DELETE /sandbox/{id}
Docs: https://www.daytona.io/docs
"""
import os
import httpx


class Daytona:
    def __init__(self):
        self._api_key = os.environ["DAYTONA_API_KEY"]
        self._base = os.environ.get("DAYTONA_API_BASE", "https://app.daytona.io/api")

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def run(
        self,
        code: str,
        filename: str = "main.py",
        command: str = None,
        timeout: int = 30,
    ) -> dict:
        async with httpx.AsyncClient(timeout=timeout + 10, headers=self._headers) as client:
            # 1. Create sandbox
            resp = await client.post(f"{self._base}/sandbox")
            resp.raise_for_status()
            sandbox_id = resp.json()["id"]

            try:
                # 2. Write file into sandbox
                resp = await client.post(
                    f"{self._base}/sandbox/{sandbox_id}/files",
                    json={"path": filename, "content": code},
                )
                resp.raise_for_status()

                # 3. Execute
                resp = await client.post(
                    f"{self._base}/sandbox/{sandbox_id}/exec",
                    json={"command": command or f"python {filename}"},
                )
                resp.raise_for_status()
                result = resp.json()
            finally:
                # 4. Always clean up the sandbox
                await client.delete(f"{self._base}/sandbox/{sandbox_id}")

        return {
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code", -1),
        }
