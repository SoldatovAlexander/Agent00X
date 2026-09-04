#!/usr/bin/env python3
"""Validate GitHub App Broker metadata without reading or printing the key."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_app import GitHubAppBrokerConfig, GitHubAppConfigurationError


def main() -> int:
    try:
        config = GitHubAppBrokerConfig.from_environment()
    except GitHubAppConfigurationError as error:
        print(f"GitHub App Broker preflight failed: {error}", file=sys.stderr)
        return 2
    print(
        "GitHub App Broker preflight passed "
        f"for installation {config.installation_id} and repository {config.repository}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
