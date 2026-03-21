from __future__ import annotations

import pytest

from py_builder_relayer_client.models import OperationType

from trading.relayer import (
    RelayerError,
    build_relayer_auth_headers,
    build_safe_call,
    relayer_auth_configured,
)


def test_relayer_auth_configured_requires_key_and_address():
    assert relayer_auth_configured("test-key", "0x1111111111111111111111111111111111111111") is True
    assert relayer_auth_configured("", "0x1111111111111111111111111111111111111111") is False
    assert relayer_auth_configured("test-key", "") is False


def test_build_relayer_auth_headers_requires_key_and_address():
    with pytest.raises(RelayerError):
        build_relayer_auth_headers("", "0x1111111111111111111111111111111111111111")

    with pytest.raises(RelayerError):
        build_relayer_auth_headers("test-key", "")


def test_build_relayer_auth_headers_returns_expected_header_names():
    headers = build_relayer_auth_headers(
        "test-key",
        "0x1111111111111111111111111111111111111111",
    )
    assert headers == {
        "RELAYER_API_KEY": "test-key",
        "RELAYER_API_KEY_ADDRESS": "0x1111111111111111111111111111111111111111",
        "Content-Type": "application/json",
    }


def test_build_safe_call_uses_call_operation():
    tx = build_safe_call("0x2222222222222222222222222222222222222222", "0xdeadbeef")
    assert tx.to == "0x2222222222222222222222222222222222222222"
    assert tx.data == "0xdeadbeef"
    assert tx.value == "0"
    assert tx.operation == OperationType.Call

