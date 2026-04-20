from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Kafka — source topics
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_entso_e_raw: str = "grid.entso-e.raw"
    kafka_group_id: str = "kama-grid-normalizer"

    # Kafka — output topic
    kafka_topic_normalized: str = "grid.normalized"

    # TimescaleDB
    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"

    # Schema Registry (Confluent-compatible)
    schema_registry_url: str = "http://schema-registry:8081"

    # Batch controls
    batch_size: int = 200
    batch_flush_interval_sec: float = 5.0


settings = Settings()
