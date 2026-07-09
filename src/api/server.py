"""CFA-Agent FastAPI 应用实例"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.logging_middleware import LoggingMiddleware
from src.api.routes.agent_routes import router as agent_router
from src.api.routes.task_routes import router as task_router
from src.api.routes.tool_routes import router as tool_router
from src.api.routes.skill_routes import router as skill_router
from src.api.routes.mcp_routes import router as mcp_router
from src.api.routes.chat_routes import router as chat_router
from src.agents.service import init_agent_service
from src.common.settings import get_config
from src.db.connection import get_db, close_db
from src.db.schema import init_database, check_database_schema
from src.skills.registry import get_skill_registry, load_skills_from_directory
from src.tools.loader import initialize_builtin_tools

logging.basicConfig(
    level=get_config().log.level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("cfa-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting CFA-Agent...")

    db = await get_db()
    if not await check_database_schema(db):
        logger.info("Initializing database schema...")
        await init_database(db)
        logger.info("Database schema initialized")
    else:
        logger.info("Database schema already exists")

    logger.info("Initializing agent service from config...")
    agent_service = init_agent_service("config/agents.yaml")
    logger.info("AgentService initialized with %d agents", agent_service.size)

    tool_count = await initialize_builtin_tools()
    logger.info("Initialized %d builtin tools", tool_count)

    skill_count = await load_skills_from_directory("config/skills")
    registry = get_skill_registry()
    logger.info("Loaded %d skills into global registry", skill_count)
    for skill in registry.list_all():
        logger.info("  - %s: triggers=%s", skill.get("name"), skill.get("triggers"))
    for agent_id in agent_service.list_ids():
        config = agent_service.get(agent_id)
        if config:
            logger.info("  - %s: %s (entry=%s, verify=%s)",
                        config.id, config.name, config.is_entry_point, config.enable_verify)

    yield

    logger.info("Shutting down CFA-Agent...")
    await close_db()
    logger.info("Database connection closed")


app = FastAPI(
    title="CFA-Agent API",
    description="自主决策智能体集群系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(LoggingMiddleware)

app.include_router(agent_router)
app.include_router(task_router)
app.include_router(tool_router)
app.include_router(skill_router)
app.include_router(mcp_router)
app.include_router(chat_router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "CFA-Agent",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}