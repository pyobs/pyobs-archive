"""pyobs-auth USER_RESOLVER for archive.

Keycloak's `sub` claim is the join key (see pyobs-core's shared-auth design doc), stored on
Profile.keycloak_sub. On first Keycloak login for an existing observation-portal-era account
(matched by email), the two get linked rather than minting a second, disconnected User.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User

from pyobs_archive.authentication.models import Profile


def resolve_user(claims: dict[str, Any]) -> User | None:
    sub = claims["sub"]

    try:
        return Profile.objects.get(keycloak_sub=sub).user
    except Profile.DoesNotExist:
        pass

    email = claims.get("email")
    user = User.objects.filter(email=email).first() if email else None

    if user is None:
        username = claims.get("preferred_username") or sub
        user = User.objects.create(username=username, email=email or "", is_active=True)

    Profile.objects.update_or_create(user=user, defaults={"keycloak_sub": sub})
    return user
