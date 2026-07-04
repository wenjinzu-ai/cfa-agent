from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

_COMMON_CONFIG = {"env_file": ".env", "extra": "ignore", "populate_by_name": True}


class LLMConfig(BaseSettings):
    api_key: str = Field(default="sk-placeholder", alias="OPENAI_API_KEY", description="OpenAI API Key")
    base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    model_reasoning: str = Field(default="gpt-4o", alias="OPENAI_MODEL_REASONING")
    max_tokens_per_request: int = Field(default=4096, alias="OPENAI_MAX_TOKENS_PER_REQUEST")
    temperature: float = Field(default=0.7, alias="OPENAI_TEMPERATURE")

    model_config = _COMMON_CONFIG


class AppConfig(BaseSettings):
    host: str = Field(default="127.0.0.1", alias="APP_HOST")
    port: int = Field(default=8000, alias="APP_PORT")
    debug: bool = Field(default=True, alias="APP_DEBUG")

    model_config = _COMMON_CONFIG


class DatabaseConfig(BaseSettings):
    sqlite_db_path: str = Field(default="./data/cfa_agent.db", alias="SQLITE_DB_PATH")

    model_config = _COMMON_CONFIG


class LogConfig(BaseSettings):
    log_level: str = Field(default="DEBUG", alias="LOG_LEVEL")
    log_file: str = Field(default="./logs/cfa_agent.log", alias="LOG_FILE")

    model_config = _COMMON_CONFIG


class BehaviorGuardConfig(BaseSettings):
    max_steps: int = Field(default=20, alias="BEHAVIOR_MAX_STEPS")
    token_budget: int = Field(default=50000, alias="BEHAVIOR_TOKEN_BUDGET")
    consecutive_deviation_limit: int = Field(default=5, alias="BEHAVIOR_CONSECUTIVE_DEVIATION_LIMIT")

    model_config = _COMMON_CONFIG


class Config:
    def __init__(self):
        self.llm = LLMConfig()
        self.app = AppConfig()
        self.database = DatabaseConfig()
        self.log = LogConfig()
        self.behavior_guard = BehaviorGuardConfig()

    @classmethod
    def reset(cls):
        get_config.cache_clear()


@lru_cache
def get_config():
    return Config()