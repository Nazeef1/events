from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://eventsphere:eventsphere@postgres:5432/identity_db"
    jwt_secret: str = "dev-insecure-secret-change-me"
    service_name: str = "identity-service"
    cors_origins: list[str] = ["http://localhost:3000"]

    # When both are set, this account is created as ADMIN at startup if missing.
    admin_email: str = ""
    admin_password: str = ""


settings = Settings()
