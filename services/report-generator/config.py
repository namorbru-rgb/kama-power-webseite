from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://kama:kama_dev@localhost:5432/kama_energy"
    # KAMA API base URL for fetching summary data
    api_base_url: str = "http://api:8000"

    # SMTP settings for weekly email delivery
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "kama-reports@kama.energy"

    # Recipients for the weekly management report
    report_recipients: str = "roman@kama.energy"

    # Cron schedule: default = Monday 07:00 Zurich time
    report_schedule: str = "0 7 * * 1"

    debug: bool = False


settings = Settings()
