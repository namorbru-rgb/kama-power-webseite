from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_telemetry: str = "telemetry.raw"
    kafka_group_id: str = "kama-ingestor"
    # Batch writes to TimescaleDB every N records or M seconds (whichever first)
    batch_size: int = 100
    batch_flush_interval_sec: float = 2.0
    # How many seconds without a heartbeat before liveness probe fails
    liveness_timeout_sec: float = 30.0


settings = Settings()
