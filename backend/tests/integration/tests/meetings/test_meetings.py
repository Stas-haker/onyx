"""Run against a disposable Onyx deployment with MEETINGS_ENABLED=true.

No cloud calls or mocks. Upload deliberately invalid media to exercise failure
handling without requiring GPU models for the API authorization checks.
"""

import os

import requests

from tests.integration.common_utils.test_models import DATestUser


def test_upload_ownership_and_export(
    admin_user: DATestUser, basic_user: DATestUser
) -> None:
    base = os.environ.get("MEETINGS_TEST_URL", "http://localhost:3000/api")
    response = requests.post(
        f"{base}/meetings",
        headers=basic_user.headers,
        files={"file": ("invalid.wav", b"not an audio file", "audio/wav")},
        data={"agenda": "Test agenda"},
        timeout=30,
    )
    response.raise_for_status()
    meeting_id = response.json()["id"]
    own = requests.get(
        f"{base}/meetings/{meeting_id}", headers=basic_user.headers, timeout=10
    )
    assert own.status_code == 200
    assert own.json()["filename"] == "invalid.wav"
    for path in (f"/{meeting_id}", f"/{meeting_id}/export?format=json"):
        forbidden = requests.get(
            f"{base}/meetings{path}", headers=admin_user.headers, timeout=10
        )
        assert forbidden.status_code == 404
    forbidden_retry = requests.post(
        f"{base}/meetings/{meeting_id}/retry", headers=admin_user.headers, timeout=10
    )
    assert forbidden_retry.status_code == 404
    export = requests.get(
        f"{base}/meetings/{meeting_id}/export?format=json",
        headers=basic_user.headers,
        timeout=10,
    )
    assert export.status_code == 200
    assert export.json()["id"] == meeting_id
    assert "attachment" in export.headers["Content-Disposition"]


def test_empty_upload_rejected(basic_user: DATestUser) -> None:
    base = os.environ.get("MEETINGS_TEST_URL", "http://localhost:3000/api")
    response = requests.post(
        f"{base}/meetings",
        headers=basic_user.headers,
        files={"file": ("empty.wav", b"", "audio/wav")},
        timeout=10,
    )
    assert response.status_code == 400
