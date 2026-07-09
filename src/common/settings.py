"""CFA-Agent 配置管理 - 基于 pydantic-settings"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    """LLM 配置"""

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    model_reasoning: str = "gpt-4o"
    max_tokens_per_request: int = 4096
    temperature: float = 0.7


class AppSettings(BaseModel):
    """应用配置"""

    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True
    name: str = "CFA-Agent"


class DatabaseSettings(BaseModel):
    """数据库配置"""

    db_path: str = "./data/cfa_agent.db"
    wal_mode: bool = True
    connection_pool_size: int = 5
    connection_timeout: float = 30.0


class LogSettings(BaseModel):
    """日志配置"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    log_file: str = "./logs/cfa_agent.log"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


class BehaviorGuardrailSettings(BaseModel):
    """行为护栏配置"""

    max_steps: int = 20
    token_budget: int = 50000
    deviation_threshold: float = 0.6
    consecutive_deviation_limit: int = 5


class Settings(BaseSettings):
    """全局配置

    使用扁平环境变量映射，兼容现有 .env 文件格式。
    环境变量命名规则：{SECTION}_{FIELD}，如 OPENAI_API_KEY, APP_HOST
    """

    # LLM 配置
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_model_reasoning: str = "gpt-4o"
    openai_max_tokens_per_request: int = 4096
    openai_temperature: float = 0.7

    # 应用配置
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_debug: bool = True

    # 数据库配置
    sqlite_db_path: str = "./data/cfa_agent.db"

    # 日志配置
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    log_file: str = "./logs/cfa_agent.log"

    # 行为护栏配置
    behavior_max_steps: int = 20
    behavior_token_budget: int = 50000
    behavior_deviation_threshold: float = 0.6
    behavior_consecutive_deviation_limit: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def llm(self) -> LLMSettings:
        """获取 LLM 配置"""
        return LLMSettings(
            api_key=self.openai_api_key,
            base_url=self.openai_base_url,
            model=self.openai_model,
            model_reasoning=self.openai_model_reasoning,
            max_tokens_per_request=self.openai_max_tokens_per_request,
            temperature=self.openai_temperature,
        )

    @property
    def app(self) -> AppSettings:
        """获取应用配置"""
        return AppSettings(
            host=self.app_host,
            port=self.app_port,
            debug=self.app_debug,
        )

    @property
    def database(self) -> DatabaseSettings:
        """获取数据库配置"""
        return DatabaseSettings(db_path=self.sqlite_db_path)

    @property
    def log(self) -> LogSettings:
        """获取日志配置"""
        return LogSettings(
            level=self.log_level,
            log_file=self.log_file,
        )

    @property
    def behavior(self) -> BehaviorGuardrailSettings:
        """获取行为护栏配置"""
        return BehaviorGuardrailSettings(
            max_steps=self.behavior_max_steps,
            token_budget=self.behavior_token_budget,
            deviation_threshold=self.behavior_deviation_threshold,
            consecutive_deviation_limit=self.behavior_consecutive_deviation_limit,
        )

    @property
    def db_absolute_path(self) -> Path:
        """获取数据库绝对路径"""
        path = Path(self.sqlite_db_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    @property
    def log_absolute_path(self) -> Path:
        """获取日志文件绝对路径"""
        path = Path(self.log_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()


@lru_cache
def get_config() -> Settings:
    """获取全局配置实例（单例模式）"""
    return Settings()


def clear_config_cache() -> None:
    """清除配置缓存（用于测试或热重载场景）"""
    get_config.cache_clear()