from __future__ import annotations

from http import HTTPStatus

from pydantic import SecretStr


def test_jobs_api_requires_bearer_token_when_configured(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        harness.settings.api_key = SecretStr("top-secret")
        harness.app.state.settings = harness.settings

        response = harness.client.post(
            "/api/v1/jobs",
            files={"file": ("meeting.wav", b"fake-audio-bytes", "audio/wav")},
        )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"


def test_jobs_api_accepts_valid_bearer_token(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        harness.settings.api_key = SecretStr("top-secret")
        harness.app.state.settings = harness.settings

        response = harness.client.post(
            "/api/v1/jobs",
            headers={"Authorization": "Bearer top-secret"},
            files={"file": ("meeting.wav", b"fake-audio-bytes", "audio/wav")},
        )

    assert response.status_code == HTTPStatus.ACCEPTED
