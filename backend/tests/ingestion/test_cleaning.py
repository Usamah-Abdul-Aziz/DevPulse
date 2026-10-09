"""Cleaning rules (blueprint §6.1, data-ethics invariant 2).

Bots and generated files are *flagged*, never deleted — so these tests assert both directions: a
rule must catch what it targets, and it must leave real work alone. A filter that silently flagged
everything would be as useless as one that flags nothing.
"""

from __future__ import annotations

import pytest

from app.ingestion.cleaning import BOT_LOGINS, is_bot_login, is_generated_path


class TestBotLogins:
    @pytest.mark.parametrize(
        "login",
        [
            "dependabot[bot]",
            "dependabot-preview[bot]",
            "renovate[bot]",
            "github-actions[bot]",
            "imgbot[bot]",
            "App-Some-New-Bot[bot]",
        ],
    )
    def test_bot_suffix_is_detected(self, login: str) -> None:
        assert is_bot_login(login) is True

    @pytest.mark.parametrize("login", sorted(BOT_LOGINS))
    def test_known_bot_logins(self, login: str) -> None:
        assert is_bot_login(login) is True

    @pytest.mark.parametrize(
        "login", ["octocat", "dependabot-contributor", "my-bot-tooling", "renovate-config", ""]
    )
    def test_people_are_not_flagged(self, login: str) -> None:
        assert is_bot_login(login) is False

    def test_matching_is_case_insensitive(self) -> None:
        assert is_bot_login("Dependabot") is True
        assert is_bot_login("ImgBot") is True

    def test_none_is_safe(self) -> None:
        assert is_bot_login(None) is False


class TestGeneratedPaths:
    @pytest.mark.parametrize(
        "path",
        [
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "Cargo.lock",
            "go.sum",
            "composer.lock",
            "Gemfile.lock",
            "frontend/package-lock.json",
            "some/nested/dir/yarn.lock",
            "dist/index.js",
            "build/main.js",
            "node_modules/react/index.js",
            "vendor/lib/foo.c",
            "assets/app.min.js",
            "assets/app.min.css",
            "coverage/lcov.info",
            "src/__snapshots__/app.test.tsx.snap",
            "app.test.tsx.snap",
            "proto/example.pb.go",
            "proto/example_pb2.py",
            "src/code.generated.ts",
            ".github/workflows/ci.yml",
        ],
    )
    def test_generated_paths_are_flagged(self, path: str) -> None:
        assert is_generated_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "backend/app/api/repositories.py",
            "frontend/components/connect-form.tsx",
            "README.md",
            "docs/decisions/ADR-008.md",
            "tests/test_cleaning.py",
            "src/lock.py",
            "src/builder.py",
            "src/generated_by_hand.py",
            "minifiers/index.js",
        ],
    )
    def test_hand_written_paths_are_left_alone(self, path: str) -> None:
        assert is_generated_path(path) is False

    def test_matching_is_case_insensitive(self) -> None:
        assert is_generated_path("Dist/Index.js") is True
        assert is_generated_path("NODE_MODULES/x.js") is True

    def test_none_is_safe(self) -> None:
        assert is_generated_path(None) is False
