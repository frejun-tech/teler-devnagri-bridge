import os

from pydantic_settings import BaseSettings
from app.utils.ngrok_utils import get_SERVER_DOMAIN

class Setting(BaseSettings):
    """Application settings"""
    
    # Devnagri configuration
    DEVNAGRI_API_KEY: str = os.getenv("DEVNAGRI_API_KEY", "")
    DEVNAGRI_WS_URL: str = os.getenv("DEVNAGRI_WS_URL")
    
    #server configuration - dynamically get ngrok URL
    @property
    def SERVER_DOMAIN(self) -> str:
        return get_SERVER_DOMAIN()
    
    server_host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port: int = int(os.getenv("SERVER_PORT", "8000"))
    
    # Teler configuration
    TELER_ACCOUNT_ID: str = os.getenv("TELER_ACCOUNT_ID")
    TELER_API_KEY: str = os.getenv("TELER_API_KEY", "")
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    
# settings instance
settings = Setting()