"""pyobs-auth USER_RESOLVER for archive.

Keycloak's `sub` claim is the join key (see pyobs-core's shared-auth design doc), stored on
Profile.keycloak_sub. On first Keycloak login for an existing observation-portal-era account
(matched by email, falling back to username), the two get linked rather than minting a second,
disconnected User. Newly-minted accounts are active by default: authorization is now the
PYOBS_AUTH['REQUIRED_GROUPS'] claims gate (Keycloak group membership), not local activation - see
pyobs-core's specs/design/shared-authz-keycloak.md. is_staff/is_superuser are untouched by this
resolver either way (see pyobs_archive.api.permissions) - archive doesn't yet sync a privilege
role from Keycloak, so those stay local-only (createsuperuser / ADMIN_USERNAME / Django admin).
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
    username = claims.get("preferred_username") or sub

    user = User.objects.filter(email=email).first() if email else None
    if user is None:
        # Falls back to username since email matching alone misses accounts that predate
        # requiring an email address (e.g. an old observation-portal-era User with no email set)
        # - without this, User.objects.create() below hits a UNIQUE constraint on username
        # instead of linking the existing account.
        user = User.objects.filter(username=username).first()
    if user is None:
        user = User.objects.create(
            username=username, email=email or "", is_active=True
        )

    Profile.objects.update_or_create(user=user, defaults={"keycloak_sub": sub})
    return user
