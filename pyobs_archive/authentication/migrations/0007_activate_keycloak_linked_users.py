from django.db import migrations


def activate_keycloak_linked_users(apps, schema_editor):
    """One-off cutover for pyobs-core issue #823: authorization is now the PYOBS_AUTH
    REQUIRED_GROUPS claims gate, not local is_active - flip any Keycloak-linked user still
    inactive from the old per-service activation gate. Scoped to Profile.keycloak_sub being set,
    so a local-only inactive account (never touched by Keycloak) is left alone - it may have been
    deliberately deactivated for reasons unrelated to this cutover.

    Not meaningfully reversible: there's no record of which of these users were inactive by
    deliberate local choice vs. only because the old activation gate defaulted new accounts to
    inactive - a reverse migration would have to guess.
    """
    User = apps.get_model("auth", "User")
    User.objects.filter(profile__keycloak_sub__isnull=False, is_active=False).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0006_profile_keycloak_sub"),
    ]

    operations = [
        migrations.RunPython(activate_keycloak_linked_users, migrations.RunPython.noop),
    ]
