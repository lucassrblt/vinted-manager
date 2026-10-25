from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vm:vm@localhost:5432/vm"
    data_dir: Path = Path("/data")
    # Cookie Secure : désactivable en local (http://localhost).
    cookie_secure: bool = True
    session_days: int = 30
    fernet_key: str = ""
    max_upload_mb: int = 15
    timezone: str = "Europe/Paris"
    log_level: str = "INFO"
    # Tâches planifiées (synchro des mails toutes les 5 min). Désactivées dans les tests.
    scheduler_actif: bool = True
    # Écoute IMAP IDLE : les mails sont lus dès leur arrivée (la synchro planifiée reste en secours).
    ecoute_temps_reel: bool = True
    intervalle_synchro_minutes: int = 5
    # IA (étape 3). IA_FACTICE=true : réponses déterministes sans appel à l'API (démo, tests e2e).
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    ia_factice: bool = False
    # Photos IA (Replicate)
    replicate_api_token: str = ""
    # Notifications push (étape 4)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"

    @field_validator("database_url")
    @classmethod
    def driver_psycopg(cls, v: str) -> str:
        # Railway fournit « postgresql:// » : on force le pilote psycopg 3.
        for prefixe in ("postgres://", "postgresql://"):
            if v.startswith(prefixe):
                return "postgresql+psycopg://" + v[len(prefixe) :]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
