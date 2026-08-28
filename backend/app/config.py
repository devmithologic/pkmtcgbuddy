"""Application configuration, read from the environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration values that change between environments.

    By inheriting from BaseSettings, pydantic-settings fills in each field by
    looking —in this order— for a system environment variable and then a line
    in the .env file. The field's name is the key's name, case-insensitive.

    If a key with no default value is missing, the app fails at startup with a
    clear message instead of blowing up later with an unexpected None.
    """

    mongodb_uri: str
    db_name: str
    cors_origins: str

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS arrives as a comma-separated string; the middleware
        expects a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# A single instance for the whole app. It's built when the module is imported,
# so a malformed .env is detected at startup, not on the first request.
settings = Settings()
