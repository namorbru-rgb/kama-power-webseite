"""Sales & Lead Agent — configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "kama-sales-lead-agent"
    # Inbound
    kafka_topic_leads_inbound: str = "kama.leads.inbound"
    kafka_topic_comm_reply: str = "kama.comm.reply_received"
    # Outbound
    kafka_topic_lead_qualified: str = "kama.sales.lead_qualified"
    kafka_topic_offer_sent: str = "kama.sales.offer_sent"
    kafka_topic_orders_confirmed: str = "kama.orders.confirmed"
    kafka_topic_comm_send: str = "kama.comm.send_request"

    # KAMA-net / Supabase
    kama_net_url: str = "https://nixakeaiibzhesdwtelw.supabase.co"
    kama_net_api_key: str = ""
    kama_net_inquiries_table: str = "app_inquiries"
    kama_net_orders_table: str = "app_orders"
    kama_net_solar_calc_table: str = "app_solar_calculations"

    # SMTP (email sending via verkauf@kama-power.com — Hostinger)
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_user: str = "verkauf@kama-power.com"
    smtp_password: str = ""
    smtp_from: str = "verkauf@kama-power.com"

    # IMAP (email receiving via verkauf@kama-power.com — Hostinger)
    imap_host: str = "imap.hostinger.com"
    imap_port: int = 993
    imap_user: str = "verkauf@kama-power.com"
    imap_password: str = ""
    imap_poll_interval_sec: int = 60

    # Lead qualification thresholds
    # Minimum estimated value to qualify (CHF)
    min_quote_value_chf: float = 5000.0
    # Swiss cantons we serve (empty = all)
    served_cantons: str = ""

    # Follow-up schedule
    followup_days_1: int = 7   # First follow-up after N days
    followup_days_2: int = 14  # Second follow-up after N days

    # Quote validity (days)
    quote_validity_days: int = 30

    # Solar calculation defaults
    solar_price_per_kwp_chf: float = 2800.0    # CHF/kWp installed
    solar_yield_kwh_per_kwp: float = 950.0     # kWh/kWp/year (Swiss average)
    solar_co2_kg_per_kwh: float = 0.128        # kg CO2 saved per kWh

    # Poll interval for scheduled follow-up checks (seconds)
    followup_poll_interval_sec: int = 3600

    debug: bool = False


settings = Settings()
