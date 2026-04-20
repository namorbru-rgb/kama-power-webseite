from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://kama:kama_dev@localhost:5432/kama_energy"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_telemetry: str = "telemetry.raw"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    debug: bool = False


settings = Settings()
