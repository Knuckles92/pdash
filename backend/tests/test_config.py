from __future__ import annotations

from app.config import Settings


def test_file_mime_allowlist_accepts_blank_env(monkeypatch):
    monkeypatch.setenv("PDASH_FILE_MIME_ALLOWLIST", "")

    settings = Settings(_env_file=None)

    assert settings.file_mime_allowlist == []


def test_file_mime_allowlist_accepts_comma_separated_env(monkeypatch):
    monkeypatch.setenv("PDASH_FILE_MIME_ALLOWLIST", "image/png, application/pdf")

    settings = Settings(_env_file=None)

    assert settings.file_mime_allowlist == ["image/png", "application/pdf"]


def test_file_mime_allowlist_accepts_json_list_env(monkeypatch):
    monkeypatch.setenv("PDASH_FILE_MIME_ALLOWLIST", '["image/png", "application/pdf"]')

    settings = Settings(_env_file=None)

    assert settings.file_mime_allowlist == ["image/png", "application/pdf"]
