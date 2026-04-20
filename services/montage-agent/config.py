"""Montage Agent — configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "kama-montage-agent"
    # Inbound
    kafka_topic_orders_confirmed: str = "kama.orders.confirmed"
    kafka_topic_procurement_delivered: str = "kama.procurement.delivered"
    kafka_topic_montage_progress: str = "kama.montage.progress"
    # Outbound
    kafka_topic_montage_assigned: str = "kama.montage.assigned"
    kafka_topic_montage_completed: str = "kama.montage.completed"
    kafka_topic_comm_send: str = "kama.comm.send_request"

    # KAMA-net / Supabase
    kama_net_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    kama_net_api_key: str = ""
    # Tables in KAMA-net used for resource data
    kama_net_technicians_table: str = "app_technicians"
    kama_net_montage_table: str = "app_montage_auftraege"

    # FileMaker (legacy read-only)
    filemaker_url: str = ""
    filemaker_db: str = "KAMA_Montage"
    filemaker_user: str = ""
    filemaker_password: str = ""

    # Telegram: group chat for installation team notifications
    telegram_team_chat_id: str = ""

    # Assignment strategy: "earliest_available" | "round_robin"
    assignment_strategy: str = "earliest_available"

    # How many days in advance to plan assignments
    planning_horizon_days: int = 14

    debug: bool = False


settings = Settings()
