from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ENTSO-E Transparency Platform
    entsoe_security_token: str = ""
    entsoe_base_url: str = "https://web-api.tp.entsoe.eu/api"
    entsoe_area_eic: str = "10YCH-SWISSGRIDC"
    entsoe_timeout_sec: float = 30.0

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_grid: str = "grid.entso-e.raw"

    # InfluxDB 2.x
    influx_url: str = "http://influxdb:8086"
    influx_token: str = "kama_dev_token"
    influx_org: str = "kama"
    influx_bucket: str = "grid_switzerland"

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_sec: float = 300.0


settings = Settings()
