import os
import time

import boto3
import jwt

ISSUER = os.getenv("JWT_ISSUER", "cloud-operations")
AUDIENCE = os.getenv("JWT_AUDIENCE", "orders-api")
TOKEN_TTL_SECONDS = 600


def load_signing_key():
    parameter_name = os.getenv("JWT_SIGNING_KEY_PARAMETER")
    if parameter_name:
        response = boto3.client("ssm", region_name=os.getenv("AWS_REGION") or None).get_parameter(
            Name=parameter_name, WithDecryption=True
        )
        key = response["Parameter"]["Value"]
    else:
        key = os.getenv("JWT_SIGNING_KEY", "")
    if len(key.encode("utf-8")) < 32:
        raise RuntimeError("JWT signing key must be at least 32 bytes")
    return key


SIGNING_KEY = load_signing_key()


def create_access_token(subject="orders-api-client"):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": subject,
            "iat": now,
            "exp": now + TOKEN_TTL_SECONDS,
        },
        SIGNING_KEY,
        algorithm="HS256",
    )