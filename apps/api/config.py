from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://kama:kama_dev@localhost:5432/kama_energy"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_telemetry: str = "telemetry.raw"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    debug: bool = False

    # Supabase / KAMA-net — read-only (anon key only, never service-role key here)
    supabase_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    supabase_anon_key: str = ""          # set via SUPABASE_ANON_KEY or KAMA_NET_API_KEY
    supabase_timeout_sec: float = 10.0


settings = Settings()
