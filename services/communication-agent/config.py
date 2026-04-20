"""Communication Agent — configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "kama-communication-agent"
    kafka_topic_comm_send: str = "kama.comm.send_request"
    kafka_topic_comm_sent: str = "kama.comm.message_sent"
    kafka_topic_comm_reply: str = "kama.comm.reply_received"
    kafka_topic_comm_sop: str = "kama.comm.sop_created"
    # Also listen for downstream events needing notifications
    kafka_topic_procurement_ordered: str = "kama.procurement.ordered"
    kafka_topic_procurement_delivered: str = "kama.procurement.delivered"

    # SMTP — outbound (verwaltung@kama-power.com — Hostinger)
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_user: str = "verwaltung@kama-power.com"
    smtp_password: str = ""
    smtp_from: str = "verwaltung@kama-power.com"

    # IMAP — inbound polling (verwaltung@kama-power.com — Hostinger)
    imap_host: str = "imap.hostinger.com"
    imap_port: int = 993
    imap_user: str = "verwaltung@kama-power.com"
    imap_password: str = ""
    imap_poll_interval_sec: int = 60

    # Telegram
    telegram_bot_token: str = ""
    # Roman's personal chat ID (main channel)
    telegram_roman_chat_id: str = ""
    # Optional group chat for employees
    telegram_group_chat_id: str = ""

    # KAMA-net / Supabase
    kama_net_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    kama_net_api_key: str = ""
    # Supabase table for SOP storage
    kama_net_sop_table: str = "sops"

    # Paperclip (for creating internal task issues)
    paperclip_api_url: str = "http://localhost:3100"
    paperclip_api_key: str = ""
    paperclip_company_id: str = ""
    paperclip_agent_id: str = ""
    paperclip_default_project_id: str = ""
    paperclip_default_goal_id: str = ""

    debug: bool = False


settings = Settings()
