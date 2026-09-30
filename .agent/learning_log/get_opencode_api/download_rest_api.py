import asyncio
import httpx
import json
from pathlib import Path

client = httpx.AsyncClient()

file_path = Path(__file__).resolve()
download_path = file_path.parent / "opencode_rest_api.json"
port = 20001

async def get_rest_api_doc():
    response = await client.get(
        f"http://localhost:{port}/doc",
    )
    response.raise_for_status()
    body = response.json()

    print(body)
    with open(
        download_path,
        "w",
        encoding="utf‑8",
    ) as f:
        f.write(json.dumps(body, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(get_rest_api_doc())