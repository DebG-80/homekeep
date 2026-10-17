"""Cognito global sign-out after a revocation or purge (FR-20-AC2, FR-24-AC1; TDD §9.1).

Membership is re-read on every request, so access already ends when the record changes; signing
out also stops the refresh token from issuing new access tokens. The task role allows exactly
`AdminUserGlobalSignOut` and `AdminDisableUser` on the pool (infra-contract §6.1). Without a pool
(ENV=local) this does nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Any

import boto3

from app.config import Settings
from app.logging import log_error, log_event


def build_sign_out(settings: Settings) -> Callable[[str], None]:
    pool_id = settings.cognito_user_pool_id
    if settings.env == "local" or not pool_id:
        return lambda username: None

    @cache
    def client() -> Any:  # created on first use, so building the app makes no AWS call
        return boto3.client("cognito-idp", region_name=settings.aws_region)

    def sign_out(username: str) -> None:
        try:
            client().admin_user_global_sign_out(UserPoolId=pool_id, Username=username)
            log_event("SIGN_OUT", result="OK")
        except Exception as exc:  # access has already ended through the membership record
            log_error("SIGN_OUT_FAILED", exc)

    return sign_out
