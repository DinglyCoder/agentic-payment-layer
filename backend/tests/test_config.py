import pytest
from pydantic import ValidationError

from app.config import Settings


def test_complete_chain_configuration_is_available_alongside_simulation():
    settings = Settings(
        _env_file=None,
        simulation_mode=True,
        testnet_enabled=True,
        sepolia_rpc_url="https://rpc.example",
        escrow_contract_address="0x1111111111111111111111111111111111111111",
        payment_token_address="0x2222222222222222222222222222222222222222",
        arbitrator_private_key="0x1234",
    )
    assert settings.chain_enabled is True


def test_testnet_default_still_requires_complete_chain_configuration():
    with pytest.raises(ValidationError, match="Sepolia mode requires"):
        Settings(_env_file=None, simulation_mode=False)


def test_managed_demo_wallet_requires_an_explicit_key():
    with pytest.raises(ValidationError, match="DEPLOYER_PRIVATE_KEY"):
        Settings(
            _env_file=None,
            simulation_mode=True,
            testnet_enabled=True,
            sepolia_rpc_url="https://rpc.example",
            escrow_contract_address="0x1111111111111111111111111111111111111111",
            payment_token_address="0x2222222222222222222222222222222222222222",
            arbitrator_private_key="0x1234",
            managed_demo_wallet_enabled=True,
        )
