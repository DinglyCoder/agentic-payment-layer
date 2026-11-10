from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Paradime"
    app_version: str = "0.2.0"
    simulation_mode: bool = True
    testnet_enabled: bool = False
    database_url: str = "sqlite+aiosqlite:///./paradime.db"
    frontend_origin: str = "http://localhost:5173"
    seed_demo_data: bool = True

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5"

    sepolia_rpc_url: str | None = None
    escrow_contract_address: str | None = None
    payment_token_address: str | None = None
    arbitrator_private_key: SecretStr | None = None
    deployer_private_key: SecretStr | None = None
    autonomous_buyer_private_key: SecretStr | None = None
    managed_demo_wallet_enabled: bool = False
    managed_demo_max_amount_units: int = 50_000_000
    managed_demo_session_budget_units: int = 100_000_000
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

    simulation_token_address: str = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
    seller_address: str | None = None
    simulation_seller_address: str = "0x2222222222222222222222222222222222222222"
    seller_service: str = "text-analysis-v1"
    seller_price_units: int = 1_000_000
    autonomous_purchase_timeout_seconds: int = 180

    @property
    def chain_enabled(self) -> bool:
        return (self.testnet_enabled or not self.simulation_mode) and all(
            (
                self.sepolia_rpc_url,
                self.escrow_contract_address,
                self.payment_token_address,
                self.arbitrator_private_key,
            )
        )

    @property
    def managed_demo_wallet_available(self) -> bool:
        return (
            self.chain_enabled
            and self.managed_demo_wallet_enabled
            and bool(self.deployer_private_key)
        )

    @model_validator(mode="after")
    def validate_chain_settings(self) -> "Settings":
        if self.testnet_enabled or not self.simulation_mode:
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
        if self.chain_enabled:
            if self.managed_demo_wallet_enabled and not self.deployer_private_key:
                raise ValueError(
                    "DEPLOYER_PRIVATE_KEY is required when the managed demo wallet is enabled"
                )
            if self.autonomous_buyer_private_key and not self.seller_address:
                raise ValueError(
                    "SELLER_ADDRESS is required when autonomous Sepolia buying is enabled"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
