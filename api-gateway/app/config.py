from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    jwt_secret: str = "dev-insecure-secret-change-me"
    cors_origins: list[str] = ["http://localhost:3000"]

    identity_service_url: str = "http://identity-service:8000"
    event_service_url: str = "http://event-service:8000"
    booking_service_url: str = "http://booking-service:8000"
    payment_service_url: str = "http://payment-service:8000"
    notification_service_url: str = "http://notification-service:8000"
    refund_service_url: str = "http://refund-service:8000"
    analytics_service_url: str = "http://analytics-service:8000"

    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    auth_rate_limit_requests: int = 20  # login/register, per IP per window


settings = Settings()

# Longest-prefix-first routing table: incoming path "/api/<prefix>/..."
# is forwarded to the matching service with "/api" stripped.
ROUTES: list[tuple[str, str]] = [
    ("/auth", "identity_service_url"),
    ("/users", "identity_service_url"),
    ("/events", "event_service_url"),
    ("/bookings", "booking_service_url"),
    ("/payments", "payment_service_url"),
    ("/notifications", "notification_service_url"),
    ("/refunds", "refund_service_url"),
    ("/analytics", "analytics_service_url"),
]
