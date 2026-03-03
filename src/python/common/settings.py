import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "bruce_rag")
    db_user: str = os.getenv("DB_USER", "bruce")
    db_password: str = os.getenv("DB_PASSWORD", "secretpassword")

    bruce_endpoint: str = os.getenv("BRUCE_ENDPOINT", "http://localhost:8003")
    assembler_endpoint: str = os.getenv("ASSEMBLER_ENDPOINT", "http://localhost:8000")
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "9998"))

    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    whitelist_mode: str = os.getenv("WHITELIST_MODE", "exact")
    max_pending_jobs: int = int(os.getenv("MAX_PENDING_JOBS", "50"))

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


SETTINGS = Settings()
