"""
Nosana distributed GPU client — ML training and compute jobs.
Submits a job and polls GET /job/{id} until status == "completed".
Docs: https://docs.nosana.io
"""
import os
import asyncio
import httpx


class Nosana:
    def __init__(self):
        self._api_key = os.environ["NOSANA_API_KEY"]
        self._base = os.environ.get("NOSANA_API_BASE", "https://api.nosana.io/v1")

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def submit_job(
        self,
        member: str,
        image: str = "pytorch/pytorch",
        script: str = "python train.py",
        **kwargs,
    ) -> dict:
        payload = {"image": image, "script": script, "gpu": True}
        async with httpx.AsyncClient(timeout=30, headers=self._headers) as client:
            resp = await client.post(f"{self._base}/job", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return {"job_id": data.get("id"), "status": data.get("status"), "member": member}

    async def get_job_status(self, job_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10, headers=self._headers) as client:
            resp = await client.get(f"{self._base}/job/{job_id}")
            resp.raise_for_status()
            return resp.json()

    async def wait_for_completion(
        self, job_id: str, poll_interval: int = 10, max_wait: int = 3600
    ) -> dict:
        elapsed = 0
        while elapsed < max_wait:
            data = await self.get_job_status(job_id)
            if data.get("status") == "completed":
                return data
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        raise TimeoutError(f"Nosana job {job_id} did not complete within {max_wait}s")
