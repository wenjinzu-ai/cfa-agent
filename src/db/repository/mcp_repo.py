"""CFA-Agent MCP Server Repository

封装 mcp_servers 表和 mcp_tools 表的数据访问操作
"""
from __future__ import annotations

from src.db.connection import DatabaseConnection
from src.db.repository.base_repo import BaseRepository
from src.common.types import MCPStatus, MCPTransport


class MCPRepository(BaseRepository):
    """MCP Server Repository"""

    def __init__(self, db: DatabaseConnection):
        super().__init__(db)

    async def create_server(
        self,
        name: str,
        transport: MCPTransport,
        config: dict | None = None,
    ) -> dict:
        """注册 MCP Server"""
        await self.execute(
            """
            INSERT INTO mcp_servers (name, transport, config, status)
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                transport.value,
                self._json_dumps(config),
                MCPStatus.DISCONNECTED.value,
            ),
        )
        await self.commit()
        return await self.get_server_by_name(name)

    async def get_server_by_name(self, name: str) -> dict | None:
        """根据名称获取 MCP Server"""
        row = await self.fetch_one(
            "SELECT * FROM mcp_servers WHERE name = ?", (name,)
        )
        if row:
            row["config"] = self._json_loads(row.get("config"))
        return row

    async def get_all_servers(self) -> list[dict]:
        """获取所有 MCP Server"""
        rows = await self.fetch_all("SELECT * FROM mcp_servers ORDER BY name")
        for row in rows:
            row["config"] = self._json_loads(row.get("config"))
        return rows

    async def update_status(self, name: str, status: MCPStatus) -> bool:
        """更新 MCP Server 状态"""
        await self.execute(
            "UPDATE mcp_servers SET status = ? WHERE name = ?",
            (status.value, name),
        )
        await self.commit()
        return True

    async def delete_server(self, name: str) -> bool:
        """删除 MCP Server"""
        await self.execute("DELETE FROM mcp_servers WHERE name = ?", (name,))
        await self.commit()
        return True

    # ---- MCP 工具缓存 ----

    async def cache_tool(
        self,
        server_id: int,
        tool_name: str,
        tool_schema: dict | None = None,
        is_available: bool = True,
    ) -> None:
        """缓存 MCP 工具信息"""
        await self.execute(
            """
            INSERT OR REPLACE INTO mcp_tools (server_id, tool_name, tool_schema, is_available)
            VALUES (?, ?, ?, ?)
            """,
            (server_id, tool_name, self._json_dumps(tool_schema), is_available),
        )
        await self.commit()

    async def get_cached_tools(self, server_name: str) -> list[dict]:
        """获取 MCP Server 的缓存工具列表"""
        rows = await self.fetch_all(
            """
            SELECT t.* FROM mcp_tools t
            JOIN mcp_servers s ON t.server_id = s.id
            WHERE s.name = ?
            ORDER BY t.tool_name
            """,
            (server_name,),
        )
        for row in rows:
            row["tool_schema"] = self._json_loads(row.get("tool_schema"))
        return rows