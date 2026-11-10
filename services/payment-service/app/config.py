from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://eventsphere:eventsphere@postgres:5432/payment_db"
    jwt_secret: str = "dev-insecure-secret-change-me"
    service_name: str = "payment-service"
    cors_origins: list[str] = ["http://localhost:3000"]
    booking_service_url: str = "http://booking-service:8000"

    # Razorpay TEST MODE credentials. Get these from
    # https://dashboard.razorpay.com/app/keys (toggle "Test Mode" on).
    # NEVER commit real values - see .env.example.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    currency: str = "INR"

    # "mock" simulates the gateway locally so checkout works without Razorpay
    # keys. It hands out free tickets by design, so production refuses it.
    payment_mode: Literal["razorpay", "mock"] = "razorpay"
    environment: str = "development"

    @model_validator(mode="after")
    def _forbid_mock_in_production(self):
        if self.payment_mode == "mock" and self.environment == "production":
            raise ValueError("PAYMENT_MODE=mock is not allowed when ENVIRONMENT=production")
        return self


settings = Settings()
