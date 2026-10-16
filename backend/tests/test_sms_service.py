"""SMS must fail closed in a clean public deployment."""

import pytest

from app.services import sms_service
from app.services.sms_service import SmsService


@pytest.mark.asyncio
async def test_unconfigured_sms_does_not_store_or_log_code(caplog) -> None:
    service = SmsService()

    with caplog.at_level("INFO"):
        assert await service.send_verification("+8613800138000") is False

    assert service._code_store == {}
    assert "13800138000" not in caplog.text
    assert "code" not in caplog.text.lower()


def test_sms_provider_configuration_requires_sdk_and_both_credentials(monkeypatch) -> None:
    monkeypatch.setattr(sms_service, "ALIBABA_SDK_AVAILABLE", True)
    assert SmsService(access_key_id="id", access_key_secret="secret").is_configured
    assert not SmsService(access_key_id="id").is_configured
