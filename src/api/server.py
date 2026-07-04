from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes.chat import router as chat_router
from src.common.config import get_config
from src.common.logger import logger
from src.core.agent import Agent
from src.llm.openai_adapter import OpenAIAdapter
from src.memory.sqlite_store import SQLiteStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.api.deps import set_agent

    config = get_config()
    store = SQLiteStore(config.database.sqlite_db_path)
    await store.initialize()
    llm = OpenAIAdapter()
    agent = Agent(store=store, llm=llm)
    set_agent(agent)
    logger.info("CFA-Agent started")
    yield
    await llm.close()
    await store.close()
    set_agent(None)
    logger.info("CFA-Agent stopped")


app = FastAPI(
    title="CFA-Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat_router, prefix="/api/v1")