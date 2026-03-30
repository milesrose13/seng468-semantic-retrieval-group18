from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# This file was created using information from https://docs.pydantic.dev/latest/concepts/pydantic_settings/
# This was also referred to: https://docs.pydantic.dev/latest/concepts/types/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent
        / ".env"  # fix provided by claude because couldnt find the file
    )
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str

    # for utils.py
    # To generate this
    # openssl rand -hex 32
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # MinIO (object storage)
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str

    # RabbitMQ (message queue)
    RABBITMQ_URL: str
    RABBITMQ_USER: str
    RABBITMQ_PASS: str
    QUEUE_NAME: str

    # Qdrant (vector database)
    QDRANT_URL: str
    QDRANT_COLLECTION: str

    # Redis (caching)
    REDIS_URL: str = "redis://redis:6379/0"
    CACHE_ENABLED: bool = True


settings = Settings()
