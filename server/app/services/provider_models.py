import httpx
from fastapi import HTTPException


async def discover_models(
    client: httpx.AsyncClient, base_url: str, protocol: str, api_key: str
) -> list[str]:
    headers = {"Accept": "application/json"}
    params: dict[str, str | int] = {}
    if protocol == "anthropic":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        params["limit"] = 1000
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    models: set[str] = set()
    cursors: set[str] = set()
    for _ in range(10):
        try:
            response = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers,
                params=dict(params),
                timeout=httpx.Timeout(20, connect=10),
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="获取模型列表超时，请稍后重试") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="无法连接上游获取模型列表") from exc
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=400, detail="上游鉴权失败，请检查 API Key、地域与上游地址是否匹配"
            )
        if response.status_code in (404, 405):
            raise HTTPException(
                status_code=400, detail="上游不支持获取模型列表，可选择常用模型或手动输入模型 ID"
            )
        if not response.is_success:
            raise HTTPException(
                status_code=502,
                detail=f"获取模型列表失败（上游状态码 {response.status_code}）",
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="上游返回了无效的模型列表") from exc
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise HTTPException(status_code=502, detail="上游返回了无法识别的模型列表")
        for item in data["data"]:
            model_id = item.get("id") if isinstance(item, dict) else None
            if isinstance(model_id, str) and 0 < len(model_id.strip()) <= 128:
                models.add(model_id.strip())
        if protocol != "anthropic" or not data.get("has_more"):
            if not models:
                raise HTTPException(
                    status_code=400, detail="上游未返回可选模型，请检查 Key 权限或手动输入模型 ID"
                )
            return sorted(models, key=str.casefold)
        cursor = data.get("last_id")
        if not isinstance(cursor, str) or not cursor or cursor in cursors:
            raise HTTPException(status_code=502, detail="上游模型列表的分页信息无效")
        cursors.add(cursor)
        params["after_id"] = cursor
    raise HTTPException(status_code=502, detail="上游模型列表分页过多，请手动输入模型 ID")
