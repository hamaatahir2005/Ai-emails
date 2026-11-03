from functools import lru_cache
from pydantic import Field, model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://emailos:emailos@localhost:5432/emailos"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=32)
    encryption_key: str
    unsubscribe_secret: str = Field(min_length=32)
    webhook_token: str = Field(min_length=32)
    public_url: str = "https://localhost"
    access_token_minutes: int = Field(default=30, ge=5, le=60)
    sending_enabled: bool = False
    gemini_model: str = "gemini-2.5-flash"
    mailbox_host: str = ""
    mailbox_user: str = ""
    mailbox_password: str = ""
    mailbox_folder: str = "INBOX"
    mailbox_port: int = 993
    @field_validator("jwt_secret", "unsubscribe_secret", "webhook_token")
    @classmethod
    def reject_placeholders(cls, value):
        if "REPLACE" in value.upper() or "CHANGE_ME" in value.upper():
            raise ValueError("Replace example secrets with independently generated random values")
        return value
    @model_validator(mode="after")
    def secure_url(self):
        if len({self.jwt_secret, self.unsubscribe_secret, self.webhook_token}) != 3:
            raise ValueError("Security secrets must be independent")
        if not self.public_url.startswith("https://"):
            raise ValueError("PUBLIC_URL must use HTTPS")
        from cryptography.fernet import Fernet
        Fernet(self.encryption_key.encode())
        return self

@lru_cache
def config():
    return Config()
