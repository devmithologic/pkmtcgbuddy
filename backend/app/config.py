"""Configuración de la aplicación, leída del entorno."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de configuración que cambian entre entornos.

    Al heredar de BaseSettings, pydantic-settings rellena cada campo buscando —en
    este orden— una variable de entorno del sistema y luego una línea del fichero
    .env. El nombre del campo es el nombre de la clave, sin distinguir mayúsculas.

    Si falta una clave sin valor por defecto, la app falla al arrancar con un
    mensaje claro en vez de reventar más tarde con un None inesperado.
    """

    mongodb_uri: str
    db_name: str
    cors_origins: str

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS llega como una cadena separada por comas; el middleware
        espera una lista."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Una sola instancia para toda la app. Se construye al importar el módulo, así que
# un .env mal formado se detecta al arrancar, no en la primera petición.
settings = Settings()
