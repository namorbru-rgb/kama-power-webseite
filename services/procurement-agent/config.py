"""Procurement Agent — configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_orders_confirmed: str = "kama.orders.confirmed"
    kafka_topic_procurement_ordered: str = "kama.procurement.ordered"
    kafka_topic_procurement_delivered: str = "kama.procurement.delivered"
    kafka_group_id: str = "kama-procurement-agent"

    # KAMA-net / Supabase
    kama_net_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    kama_net_api_key: str = ""

    # SMTP (himalaya / puk@kama-power.com)
    smtp_host: str = "mail.kama-power.com"
    smtp_port: int = 587
    smtp_user: str = "puk@kama-power.com"
    smtp_password: str = ""
    smtp_from: str = "puk@kama-power.com"

    # Delivery tracking: warn N days before expected delivery
    delivery_warn_days: int = 2

    debug: bool = False


settings = Settings()
