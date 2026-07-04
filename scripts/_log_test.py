import httpx
import asyncio
import json


async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            "http://127.0.0.1:8000/api/v1/chat",
            json={"message": "帮我搜索一下Python最新版本", "session_id": "log-test-1"},
        )
        print(f"Status: {r.status_code}")
        d = r.json()
        print(f"Reply: {d['reply'][:300]}")
        print(f"Steps: {d.get('steps_executed', 0)}")


asyncio.run(main())