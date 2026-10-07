from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://wxspot:wxspot@localhost:5432/wxspot"
    environment: str = "development"
    media_dir: Path = Path("media")
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "auto"
    s3_addressing_style: str = "path"
    nws_user_agent: str = "WxSpot/0.1 (https://github.com/michaelhmiv/WxSpot)"
    radar_base_url: str = "https://opengeo.ncep.noaa.gov/geoserver"
    alerts_url: str = "https://api.weather.gov/alerts/active"
    geocoder_provider: str = "nominatim"
    geocoder_base_url: str = "https://nominatim.openstreetmap.org"
    geocoder_user_agent: str = "WxSpot/0.1 (https://github.com/michaelhmiv/WxSpot)"
    radar_station_catalog_url: str = (
        "https://coast.noaa.gov/arcgis/rest/services/Hosted/"
        "WeatherRadarStations/FeatureServer/0/query"
    )
    basemap_tiles: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    session_seconds: int = 604800

    @model_validator(mode="after")
    def normalize(self):
        if self.database_url.startswith(("postgres://", "postgresql://")):
            self.database_url = "postgresql+psycopg://" + self.database_url.split("://", 1)[1]
        if self.environment == "production" and not all(
            (self.s3_endpoint, self.s3_bucket, self.s3_access_key, self.s3_secret_key)
        ):
            raise ValueError("Production requires durable S3-compatible media storage")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
