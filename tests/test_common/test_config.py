from src.common.config import Config, get_config, LLMConfig, AppConfig, DatabaseConfig, LogConfig, BehaviorGuardConfig


class TestLLMConfig:
    def test_default_values(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_MODEL_REASONING", raising=False)
        monkeypatch.delenv("OPENAI_MAX_TOKENS_PER_REQUEST", raising=False)
        monkeypatch.delenv("OPENAI_TEMPERATURE", raising=False)
        config = LLMConfig(_env_file=None)
        assert config.api_key == "sk-placeholder"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4o-mini"
        assert config.model_reasoning == "gpt-4o"
        assert config.max_tokens_per_request == 4096
        assert config.temperature == 0.7

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-3.5-turbo")
        config = LLMConfig()
        assert config.api_key == "sk-test-key"
        assert config.model == "gpt-3.5-turbo"

    def test_populate_by_name(self):
        config = LLMConfig(api_key="sk-direct", model="gpt-4")
        assert config.api_key == "sk-direct"
        assert config.model == "gpt-4"


class TestAppConfig:
    def test_default_values(self):
        config = AppConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.debug is True

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("APP_HOST", "0.0.0.0")
        monkeypatch.setenv("APP_PORT", "9000")
        monkeypatch.setenv("APP_DEBUG", "false")
        config = AppConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.debug is False

    def test_populate_by_name(self):
        config = AppConfig(host="0.0.0.0", port=9000)
        assert config.host == "0.0.0.0"
        assert config.port == 9000


class TestDatabaseConfig:
    def test_default_values(self):
        config = DatabaseConfig()
        assert config.sqlite_db_path == "./data/cfa_agent.db"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SQLITE_DB_PATH", "/tmp/test.db")
        config = DatabaseConfig()
        assert config.sqlite_db_path == "/tmp/test.db"

    def test_populate_by_name(self):
        config = DatabaseConfig(sqlite_db_path="/custom/path.db")
        assert config.sqlite_db_path == "/custom/path.db"


class TestLogConfig:
    def test_default_values(self):
        config = LogConfig()
        assert config.log_level == "DEBUG"
        assert config.log_file == "./logs/cfa_agent.log"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        monkeypatch.setenv("LOG_FILE", "/var/log/agent.log")
        config = LogConfig()
        assert config.log_level == "INFO"
        assert config.log_file == "/var/log/agent.log"

    def test_populate_by_name(self):
        config = LogConfig(log_level="WARNING", log_file="/tmp/test.log")
        assert config.log_level == "WARNING"
        assert config.log_file == "/tmp/test.log"


class TestBehaviorGuardConfig:
    def test_default_values(self):
        config = BehaviorGuardConfig()
        assert config.max_steps == 20
        assert config.token_budget == 50000
        assert config.deviation_threshold == 0.6
        assert config.consecutive_deviation_limit == 5

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("BEHAVIOR_MAX_STEPS", "50")
        config = BehaviorGuardConfig()
        assert config.max_steps == 50

    def test_populate_by_name(self):
        config = BehaviorGuardConfig(max_steps=30, token_budget=100000)
        assert config.max_steps == 30
        assert config.token_budget == 100000


class TestConfig:
    def test_config_aggregates_all_sub_configs(self):
        config = Config()
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.app, AppConfig)
        assert isinstance(config.database, DatabaseConfig)
        assert isinstance(config.log, LogConfig)
        assert isinstance(config.behavior_guard, BehaviorGuardConfig)

    def test_get_config_singleton(self):
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_reset_clears_cache(self):
        c1 = get_config()
        Config.reset()
        c2 = get_config()
        assert c1 is not c2