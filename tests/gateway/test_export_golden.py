"""导出格式的金标准（Golden Master）测试。

确保 /jobs/{job_id}/export 在各种格式下输出稳定的内容。
"""

from __future__ import annotations

from http import HTTPStatus

from .conftest import build_transcript_document


def test_export_txt_returns_full_text(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(result=build_transcript_document("placeholder"))
        response = harness.client.get(f"/api/v1/jobs/{job.id}/export?format=txt")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "大家好，今天讨论项目排期。"


def test_export_srt_golden_format(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(result=build_transcript_document("placeholder"))
        response = harness.client.get(f"/api/v1/jobs/{job.id}/export?format=srt")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/x-subrip"
    expected = (
        "1\n"
        "00:00:00,000 --> 00:00:01,800\n"
        "大家好，今天讨论项目排期。\n"
        "\n"
        "2\n"
        "00:00:01,800 --> 00:00:03,600\n"
        "先看预算，再看风险。"
    )
    assert response.text == expected


def test_export_vtt_golden_format(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(result=build_transcript_document("placeholder"))
        response = harness.client.get(f"/api/v1/jobs/{job.id}/export?format=vtt")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/vtt")
    expected = (
        "WEBVTT\n"
        "\n"
        "00:00:00.000 --> 00:00:01.800\n"
        "大家好，今天讨论项目排期。\n"
        "\n"
        "00:00:01.800 --> 00:00:03.600\n"
        "先看预算，再看风险。"
    )
    assert response.text == expected


def test_export_json_contains_all_fields(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(result=build_transcript_document("placeholder"))
        response = harness.client.get(f"/api/v1/jobs/{job.id}/export?format=json")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    payload = response.json()
    assert payload["job_id"] == job.id
    assert payload["language"] == "zh"
    assert payload["full_text"] == "大家好，今天讨论项目排期。"
    assert len(payload["segments"]) == 2
    assert payload["segments"][0]["speaker_id"] == "spk-1"
    assert payload["segments"][1]["speaker_id"] == "spk-2"
    assert payload["model_profile"] == "cn_meeting"


def test_export_unsupported_format_returns_400(gateway_harness_factory) -> None:
    with gateway_harness_factory() as harness:
        job = harness.create_job(result=build_transcript_document("placeholder"))
        response = harness.client.get(f"/api/v1/jobs/{job.id}/export?format=docx")

    assert response.status_code == HTTPStatus.BAD_REQUEST
