from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ADDRESS_PATTERN = r"^0x[a-fA-F0-9]{40}$"
HASH_PATTERN = r"^0x[a-fA-F0-9]{64}$"


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


class ManagedDemoPaymentCreate(BaseModel):
    receiver: str = Field(pattern=ADDRESS_PATTERN)
    amount_usdc: Decimal = Field(gt=0, le=1_000_000, decimal_places=6)
    description: str = Field(min_length=3, max_length=240)


class ManagedDemoWalletRead(BaseModel):
    enabled: bool
    address: str | None
    balance_units: str | None
    native_balance_wei: str | None = None
    max_amount_units: str
    remaining_session_budget_units: str


class ManagedDemoPaymentRead(BaseModel):
    payment_id: str
    deposit_tx_hash: str
    approval_tx_hash: str | None
    sender: str
    receiver: str
    amount_units: str


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
    risk_signals: list[dict]
    policy_version: str | None
    llm_score: int | None
    source: str
    decision_latency_ms: int | None
    resolution_attempts: int
    resolution_error: str | None

    @field_validator("deposited_at", "recall_deadline", mode="after")
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
    testnet_available: bool
    chain_id: int
    contract_address: str | None
    payment_token_address: str | None
    llm_enabled: bool
    stablecoin_symbol: str
    stablecoin_decimals: int


class IntentEnvelopeCreate(BaseModel):
    payment_id: str = Field(pattern=HASH_PATTERN)
    sender: str = Field(pattern=ADDRESS_PATTERN)
    receiver: str = Field(pattern=ADDRESS_PATTERN)
    amount_units: str = Field(pattern=r"^[1-9][0-9]*$", max_length=78)
    token: str = Field(pattern=ADDRESS_PATTERN)
    purpose: str = Field(min_length=3, max_length=240)
    service_or_sku: str = Field(min_length=1, max_length=120)
    mandate: str = Field(min_length=1, max_length=240)
    expires_at: datetime
    nonce: str = Field(pattern=HASH_PATTERN)
    metadata_hash: str = Field(pattern=HASH_PATTERN)
    signature: str = Field(pattern=r"^0x[a-fA-F0-9]{130}$")


class IntentEnvelopeRead(IntentEnvelopeCreate):
    model_config = ConfigDict(from_attributes=True)

    verified: bool


class SpendingMandateCreate(BaseModel):
    owner: str = Field(pattern=ADDRESS_PATTERN)
    delegate: str = Field(pattern=ADDRESS_PATTERN)
    token: str = Field(pattern=ADDRESS_PATTERN)
    max_amount_per_payment_units: str = Field(pattern=r"^[1-9][0-9]*$", max_length=78)
    total_budget_units: str = Field(pattern=r"^[1-9][0-9]*$", max_length=78)
    allowed_receiver: str = Field(pattern=ADDRESS_PATTERN)
    allowed_service: str = Field(min_length=1, max_length=120)
    expires_at: datetime
    nonce: str = Field(pattern=HASH_PATTERN)
    mandate_id: str = Field(pattern=HASH_PATTERN)
    signature: str = Field(pattern=r"^0x[a-fA-F0-9]{130}$")


class SpendingMandateRead(SpendingMandateCreate):
    model_config = ConfigDict(from_attributes=True)

    spent_units: str

    @field_validator("expires_at", mode="after")
    @classmethod
    def mark_mandate_datetime_as_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class AutonomousPurchaseCreate(BaseModel):
    mandate_id: str = Field(pattern=HASH_PATTERN)
    prompt: str = Field(min_length=3, max_length=1000)


class AutonomousDemoCreate(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    budget_units: str = Field(default="3000000", pattern=r"^[1-9][0-9]*$", max_length=78)


class AutonomousPurchaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    purchase_id: str
    mandate_id: str
    payment_id: str | None
    seller: str
    service: str
    prompt: str
    amount_units: str
    status: str
    x402_requirement: dict
    x402_payload: dict | None
    result: dict | None
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None

    @field_validator("created_at", "completed_at", mode="after")
    @classmethod
    def mark_purchase_datetimes_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)


class AutonomousBuyerRead(BaseModel):
    address: str | None
    enabled: bool
    mode: str
    seller_service: str
    seller_price_units: str
