from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Paradime"
    app_version: str = "0.1.0"
    simulation_mode: bool = True
    database_url: str = "sqlite+aiosqlite:///./paradime.db"
    frontend_origin: str = "http://localhost:5173"
    seed_demo_data: bool = True

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5"

    sepolia_rpc_url: str | None = None
    escrow_contract_address: str | None = None
    payment_token_address: str | None = None
    arbitrator_private_key: SecretStr | None = None
    chain_confirmations: int = 2
    chain_start_block: int | None = None
    poll_interval_seconds: float = 3.0

    stablecoin_symbol: str = "USDC"
    stablecoin_decimals: int = 6
    high_amount_units: int = 50_000_000
    medium_amount_units: int = 10_000_000
    velocity_window_seconds: int = 60
    velocity_medium_count: int = 3
    velocity_high_count: int = 5
    recall_threshold: int = 70

    @property
    def chain_enabled(self) -> bool:
        return not self.simulation_mode

    @model_validator(mode="after")
    def validate_chain_settings(self) -> "Settings":
        if self.chain_enabled:
            missing = [
                name
                for name, value in (
                    ("SEPOLIA_RPC_URL", self.sepolia_rpc_url),
                    ("ESCROW_CONTRACT_ADDRESS", self.escrow_contract_address),
                    ("PAYMENT_TOKEN_ADDRESS", self.payment_token_address),
                    ("ARBITRATOR_PRIVATE_KEY", self.arbitrator_private_key),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"Sepolia mode requires: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
