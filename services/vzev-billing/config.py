import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://kama:kama@localhost:5432/kama",
    )


settings = Settings()
