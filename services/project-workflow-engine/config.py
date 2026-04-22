"""Projekt- & Workflow-Engine — configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "kama-project-workflow-engine"
    # Inbound
    kafka_topic_orders_confirmed: str = "kama.orders.confirmed"
    kafka_topic_procurement_delivered: str = "kama.procurement.delivered"
    kafka_topic_montage_completed: str = "kama.montage.completed"
    # Outbound
    kafka_topic_workflow_step_ready: str = "kama.workflow.step_ready"
    kafka_topic_workflow_completed: str = "kama.workflow.completed"
    kafka_topic_ops_inbound_email: str = "kama.ops.inbound_email"
    kafka_topic_comm_reply: str = "kama.comm.reply_received"

    # KAMA-net / Supabase
    kama_net_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    kama_net_api_key: str = ""

    # Paperclip
    paperclip_api_url: str = "http://localhost:3000"
    paperclip_api_key: str = ""
    paperclip_company_id: str = ""
    paperclip_goal_id: str = ""         # company-level goal for all step issues
    paperclip_project_id: str = ""      # Paperclip project for all step issues

    # SMTP — outbound notifications (betrieb@kama-power.com — Hostinger)
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_user: str = "betrieb@kama-power.com"
    smtp_password: str = ""
    smtp_from: str = "betrieb@kama-power.com"

    # IMAP — inbound (betrieb@kama-power.com — Hostinger)
    imap_host: str = "imap.hostinger.com"
    imap_port: int = 993
    imap_user: str = "betrieb@kama-power.com"
    imap_password: str = ""
    imap_poll_interval_sec: int = 60

    # Agent IDs per role (resolved at startup from Paperclip API)
    # If not set, the engine falls back to role-based lookup
    agent_id_ceo: str = ""
    agent_id_cto: str = ""
    agent_id_procurement: str = ""
    agent_id_montage: str = ""
    agent_id_meldewesen: str = ""

    # Agent Memory (Supabase Langzeitspeicher)
    # Set SUPABASE_SERVICE_ROLE_KEY (Service Role secret, never expose to frontend).
    # SUPABASE_URL defaults to kama_net_url if not set separately.
    supabase_service_role_key: str = ""
    agent_memory_enabled: bool = False
    agent_memory_scope: str = "project-workflow-engine"
    # Logical agent identifier written to memory tables (defaults to kafka group id)
    agent_memory_agent_id: str = "kama-project-workflow-engine"
    # Max memory items loaded on start
    agent_memory_read_limit: int = 20

    debug: bool = False


settings = Settings()
