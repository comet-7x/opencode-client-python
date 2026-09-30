第一步：查看OpenCode版本号

```Shell
opencode -v
```


第二步：启动服务，准备获取最新的REST API 文档

```Shell
# input
❯ opencode serve --port 20001

# output
Warning: OPENCODE_SERVER_PASSWORD is not set; server is unsecured.
opencode server listening on http://127.0.0.1:20001
```


第三步：下载REST API 文档到本地，并使用：[editor.swagger.io](https://editor.swagger.io/) 网站可视化REST API 接口文档

```Python
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
```
