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

    # KAMA-net / Supabase
    kama_net_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    kama_net_api_key: str = ""

    # Paperclip
    paperclip_api_url: str = "http://localhost:3000"
    paperclip_api_key: str = ""
    paperclip_company_id: str = ""
    paperclip_goal_id: str = ""         # company-level goal for all step issues
    paperclip_project_id: str = ""      # Paperclip project for all step issues

    # Agent IDs per role (resolved at startup from Paperclip API)
    # If not set, the engine falls back to role-based lookup
    agent_id_ceo: str = ""
    agent_id_cto: str = ""
    agent_id_procurement: str = ""
    agent_id_montage: str = ""
    agent_id_meldewesen: str = ""

    debug: bool = False


settings = Settings()
