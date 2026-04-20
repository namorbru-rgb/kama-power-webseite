"""Lager & Logistik Agent — configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "kama-lager-logistik-agent"

    # Inbound topics
    kafka_topic_procurement_ordered: str = "kama.procurement.ordered"
    kafka_topic_procurement_delivered: str = "kama.procurement.delivered"
    kafka_topic_comm_reply: str = "kama.comm.reply_received"

    # Outbound topics
    kafka_topic_comm_send: str = "kama.comm.send_request"
    kafka_topic_lager_eingang: str = "kama.lager.eingang_bestaetigt"
    kafka_topic_lager_bestand: str = "kama.lager.bestand_aktualisiert"

    # KAMA-net / Supabase
    kama_net_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    kama_net_api_key: str = ""
    # Tables
    kama_net_employees_table: str = "employee_profiles"
    kama_net_articles_table: str = "app_articles"

    # Warehouse employees — Telegram chat IDs for Güttingen site
    # Comma-separated list of "name:telegram_chat_id" pairs
    # e.g. "Yasin:123456789,Marko:987654321"
    warehouse_employee_contacts: str = ""

    # Confirmation keywords (lowercase, comma-separated)
    confirmation_keywords: str = "ja,ok,bestätigt,bestaetigt,erledigt,done,geliefert,angekommen,yes"

    debug: bool = False


settings = Settings()
