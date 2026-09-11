from pydantic_settings import BaseSettings


class NotificationSettings(BaseSettings):
    """
    Configuration for the notification integration layer.

    NOTIFICATION_PROVIDER
        Which delivery provider to use.
        Allowed values: "simulator" (default)
        Future values:  "microsoft_graph"

    Defaults to "simulator" so the application runs in any environment
    without requiring external credentials.
    """
    NOTIFICATION_PROVIDER: str = "simulator"

    class Config:
        env_file = ".env"
        case_sensitive = True
