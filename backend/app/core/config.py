from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    """Application configuration and environment variables."""
    PROJECT_NAME: str = "Document Intelligence API"
    ENVIRONMENT: str = "development"
    
    # Secrets & External Services
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "nvidia/nemotron-3-ultra-550b-a55b"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:5433/doc_intelligence"
    
    # Phase 1 Locked Parameters
    OCR_FLOOR_CONFIDENCE: float = 0.3
    CONFIDENCE_REVIEW_THRESHOLD: float = 0.7
    CONFIDENCE_WEIGHT_OCR: float = 0.5
    CONFIDENCE_WEIGHT_STRING_SIM: float = 0.3
    CONFIDENCE_WEIGHT_VALIDATION: float = 0.2
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
