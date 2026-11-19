"""Firebase Authentication configuration and ID-token verification."""

import logging
import threading
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_admin_app = None
_admin_app_lock = threading.Lock()


def firebase_auth_ready() -> bool:
    """Return whether both browser and server Firebase settings are present."""
    return all((
        config.FIREBASE_WEB_API_KEY,
        config.FIREBASE_AUTH_DOMAIN,
        config.FIREBASE_PROJECT_ID,
        config.FIREBASE_APP_ID,
        config.FIREBASE_ADMIN_CLIENT_EMAIL,
        config.FIREBASE_ADMIN_PRIVATE_KEY,
    ))


def public_firebase_config() -> Dict[str, Any]:
    """Return browser-safe settings without exposing the Admin private key."""
    return {
        "configured": firebase_auth_ready(),
        "firebase": {
            "apiKey": config.FIREBASE_WEB_API_KEY,
            "authDomain": config.FIREBASE_AUTH_DOMAIN,
            "projectId": config.FIREBASE_PROJECT_ID,
            "appId": config.FIREBASE_APP_ID,
        } if firebase_auth_ready() else None,
    }


def _get_admin_app():
    global _admin_app
    if _admin_app is not None:
        return _admin_app

    if not firebase_auth_ready():
        raise RuntimeError("Firebase Authentication is not configured on the server")

    with _admin_app_lock:
        if _admin_app is not None:
            return _admin_app
        try:
            import firebase_admin

            try:
                _admin_app = firebase_admin.get_app()
            except ValueError:
                from firebase_admin import credentials

                service_account = {
                    "type": "service_account",
                    "project_id": config.FIREBASE_PROJECT_ID,
                    "private_key_id": config.FIREBASE_ADMIN_PRIVATE_KEY_ID,
                    "private_key": config.FIREBASE_ADMIN_PRIVATE_KEY,
                    "client_email": config.FIREBASE_ADMIN_CLIENT_EMAIL,
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
                credential = credentials.Certificate(service_account)
                _admin_app = firebase_admin.initialize_app(
                    credential,
                    {"projectId": config.FIREBASE_PROJECT_ID},
                )
        except Exception as exc:
            logger.exception("Could not initialize Firebase Admin SDK (%s)", type(exc).__name__)
            raise RuntimeError("Firebase Admin SDK could not be initialized") from exc
    return _admin_app


def get_firebase_admin_app():
    """Return the initialized Admin app for authenticated Firebase services."""
    return _get_admin_app()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Dict[str, Any]:
    """Verify a Firebase ID token and return its trusted claims."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        from firebase_admin import auth
        from firebase_admin.exceptions import FirebaseError
    except ImportError as exc:
        logger.exception("Firebase Admin SDK is not installed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase Authentication is unavailable on the server",
        ) from exc

    try:
        decoded = auth.verify_id_token(credentials.credentials, app=_get_admin_app())
        if not decoded.get("uid"):
            raise ValueError("Verified token did not contain a user ID")
        return decoded
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign-in token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except FirebaseError as exc:
        logger.warning("Firebase token verification unavailable (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase Authentication is temporarily unavailable",
        ) from exc
