from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ADDRESS_PATTERN = r"^0x[a-fA-F0-9]{40}$"


class DemoPaymentCreate(BaseModel):
    sender: str = Field(pattern=ADDRESS_PATTERN)
    receiver: str = Field(pattern=ADDRESS_PATTERN)
    amount_usdc: Decimal = Field(gt=0, le=1_000_000, decimal_places=6)
    description: str = Field(min_length=3, max_length=240)

    @field_validator("receiver")
    @classmethod
    def different_parties(cls, receiver: str, info) -> str:
        sender = info.data.get("sender")
        if sender and receiver.lower() == sender.lower():
            raise ValueError("sender and receiver must differ")
        return receiver


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str
    sender: str
    receiver: str
    amount_units: str
    metadata_hash: str
    description: str
    deposit_tx_hash: str
    resolution_tx_hash: str | None
    block_number: int | None
    deposited_at: datetime
    recall_deadline: datetime
    status: str
    decision: str | None
    risk_score: int | None
    risk_level: str | None
    risk_reasons: list[str]
    llm_score: int | None
    source: str
    decision_latency_ms: int | None

    @field_validator("deposited_at", "recall_deadline", mode="before")
    @classmethod
    def mark_sqlite_datetimes_as_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    address: str
    name: str
    status: str
    trust_score: int


class StatsRead(BaseModel):
    total_payments: int
    executed_payments: int
    recalled_payments: int
    protected_value_units: str
    execution_rate: float
    average_risk_score: float


class HealthRead(BaseModel):
    status: str
    mode: str
    chain_id: int
    contract_address: str | None
    llm_enabled: bool
    stablecoin_symbol: str
    stablecoin_decimals: int
