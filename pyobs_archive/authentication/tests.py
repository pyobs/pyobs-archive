from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from pyobs_archive.authentication.admin_sync import sync_admin_user
from pyobs_archive.authentication.keycloak import resolve_user
from pyobs_archive.authentication.models import Profile

# A distinct, unlikely-to-collide username -- not "admin", since a real local_settings.py
# (e.g. a developer's own ADMIN_USERNAME="admin") would already have synced an "admin" User via
# admin_sync's post_migrate hook by the time the test database exists, before any of this
# module's own override_settings is active.
_TEST_ADMIN_USERNAME = "test-sync-admin"


class ResolveUserTests(TestCase):
    def test_creates_a_new_user_on_first_login(self):
        user = resolve_user(
            {
                "sub": "sub-1",
                "email": "new@example.org",
                "preferred_username": "newperson",
            }
        )

        self.assertEqual(user.username, "newperson")
        self.assertEqual(user.email, "new@example.org")
        self.assertEqual(Profile.objects.get(user=user).keycloak_sub, "sub-1")

    def test_same_sub_resolves_to_the_same_user_on_a_later_login(self):
        first = resolve_user({"sub": "sub-2", "email": "person@example.org"})
        second = resolve_user({"sub": "sub-2", "email": "person@example.org"})

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(User.objects.filter(email="person@example.org").count(), 1)

    def test_links_an_existing_observation_portal_era_user_by_email_on_first_keycloak_login(
        self,
    ):
        existing = User.objects.create(username="oldstyle", email="legacy@example.org")

        user = resolve_user({"sub": "sub-3", "email": "legacy@example.org"})

        self.assertEqual(user.pk, existing.pk)
        self.assertEqual(Profile.objects.get(user=existing).keycloak_sub, "sub-3")

    def test_falls_back_to_sub_as_username_without_preferred_username(self):
        user = resolve_user({"sub": "sub-4", "email": "no-username@example.org"})
        self.assertEqual(user.username, "sub-4")

    def test_new_user_is_created_active(self):
        # Authorization is now the PYOBS_AUTH['REQUIRED_GROUPS'] claims gate, not local
        # activation - see pyobs-core's specs/design/shared-authz-keycloak.md.
        user = resolve_user({"sub": "sub-5", "email": "pending@example.org"})
        self.assertTrue(user.is_active)

    def test_new_user_is_not_granted_staff_or_superuser(self):
        # No Keycloak-role sync exists for archive yet - is_staff/is_superuser stay local-only.
        user = resolve_user({"sub": "sub-7", "email": "plain@example.org"})
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_links_an_existing_user_by_username_when_email_does_not_match(self):
        # e.g. an old observation-portal-era User created before an email address was required
        existing = User.objects.create(username="noemail")

        user = resolve_user(
            {
                "sub": "sub-6",
                "email": "noemail@example.org",
                "preferred_username": "noemail",
            }
        )

        self.assertEqual(user.pk, existing.pk)
        self.assertEqual(Profile.objects.get(user=existing).keycloak_sub, "sub-6")


@override_settings(ADMIN_USERNAME=_TEST_ADMIN_USERNAME, ADMIN_PASSWORD_HASH="pbkdf2_sha256$dummy")
class AdminSyncTests(TestCase):
    """admin_sync.sync_admin_user is how the settings-configured admin account (ADMIN_USERNAME/
    ADMIN_PASSWORD_HASH) gets created/kept in sync - wired to run after every
    `manage.py migrate` via the post_migrate signal (AuthenticationConfig.ready()), so a fresh
    deployment doesn't need an interactive `createsuperuser` step."""

    def test_sync_creates_a_staff_superuser_with_the_configured_password_hash(self):
        sync_admin_user(sender=None)

        user = User.objects.get(username=_TEST_ADMIN_USERNAME)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertEqual(user.password, "pbkdf2_sha256$dummy")

    def test_sync_updates_an_existing_user_that_drifted(self):
        User.objects.create(username=_TEST_ADMIN_USERNAME, is_staff=False, is_superuser=False)

        sync_admin_user(sender=None)

        user = User.objects.get(username=_TEST_ADMIN_USERNAME)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    @override_settings(ADMIN_USERNAME="", ADMIN_PASSWORD_HASH="")
    def test_sync_does_nothing_when_unconfigured(self):
        sync_admin_user(sender=None)
        self.assertFalse(User.objects.filter(username=_TEST_ADMIN_USERNAME).exists())


class ActivateKeycloakLinkedUsersMigrationTests(TestCase):
    """Exercises migration 0007's data-migration function directly against real models. This repo
    has no migration-testing framework (e.g. django-test-migrations) - the migration itself
    already ran as a no-op against an empty DB when the test database was created, so this tests
    the underlying queryset logic rather than a true forwards-migration run."""

    def test_activates_only_inactive_keycloak_linked_users(self):
        import importlib

        from django.apps import apps as django_apps

        migration_module = importlib.import_module(
            "pyobs_archive.authentication.migrations.0007_activate_keycloak_linked_users"
        )

        keycloak_inactive = User.objects.create(username="kc-inactive", is_active=False)
        Profile.objects.create(user=keycloak_inactive, keycloak_sub="sub-migrate-1")

        local_only_inactive = User.objects.create(username="local-inactive", is_active=False)
        Profile.objects.create(user=local_only_inactive, keycloak_sub=None)

        keycloak_already_active = User.objects.create(username="kc-active", is_active=True)
        Profile.objects.create(user=keycloak_already_active, keycloak_sub="sub-migrate-2")

        migration_module.activate_keycloak_linked_users(django_apps, None)

        keycloak_inactive.refresh_from_db()
        local_only_inactive.refresh_from_db()
        self.assertTrue(keycloak_inactive.is_active)
        self.assertFalse(local_only_inactive.is_active)
