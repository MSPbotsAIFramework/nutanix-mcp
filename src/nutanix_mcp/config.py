# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Process-level settings. Tenant (Prism Central) credentials are never read from here (PRD-21347)."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

HOST_HEADER = "X-Nutanix-Host"
USERNAME_HEADER = "X-Nutanix-Username"
PASSWORD_HEADER = "X-Nutanix-Password"
VERIFY_SSL_HEADER = "X-Nutanix-Verify-Ssl"

REQUIRED_HEADERS = [HOST_HEADER, USERNAME_HEADER, PASSWORD_HEADER]

# Prism Central's default HTTPS port when the host header has no explicit port.
DEFAULT_PORT = 9440


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    mcp_transport: Literal["stdio", "http"] = "http"
    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8080

    # Outbound HTTP behaviour against Prism Central.
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    max_retries: int = 3
    # Upper bound for one tool call including retries (must stay below 120s, SOP §5).
    call_budget_seconds: float = 100.0


def get_settings() -> Settings:
    return Settings()
