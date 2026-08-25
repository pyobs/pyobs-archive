import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pyobs_archive.api.portal import PortalClient, PortalUnavailable
from pyobs_archive.api.models import Project

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Mirror projects and their members/public flag from the pyobs-portal '
        '(PORTAL_URL/PORTAL_TOKEN). Run periodically (cron/systemd timer, '
        'e.g. every 5-10 min) and whenever projects change on the portal - see '
        'specs/plans/2026-08-20-archive-project-access-control.md, section 3.'
    )

    def handle(self, *args, **options):
        if not settings.PORTAL_URL or not settings.PORTAL_TOKEN:
            raise CommandError(
                'PORTAL_URL and PORTAL_TOKEN must be configured to sync projects.'
            )

        client = PortalClient(
            settings.PORTAL_URL, settings.PORTAL_TOKEN,
            timeout=settings.PORTAL_TIMEOUT
        )
        try:
            projects = client.get_projects()
        except PortalUnavailable as e:
            raise CommandError('Could not sync projects: %s' % e) from e

        # An empty response almost certainly means something's wrong on the portal side (e.g.
        # a misconfigured service account, or a transient empty page) rather than "all projects
        # were deleted" - treat it as a failure rather than wiping the local mirror. A stale
        # mirror is safer than an empty one, since PROJECT=None frames are superuser-only (D5).
        if not projects and Project.objects.exists():
            raise CommandError(
                'Portal returned zero projects while the local mirror is non-empty - refusing '
                'to wipe it. Aborting without making any changes.'
            )

        User = get_user_model()

        created, updated, unchanged = 0, 0, 0
        seen_codes = set()
        members_added, members_removed, unknown_usernames = 0, 0, set()

        with transaction.atomic():
            for payload in projects:
                code = payload['code']
                seen_codes.add(code)
                name = payload.get('name', '')
                public = bool(payload.get('public', False))
                usernames = payload.get('users', []) or []

                project, was_created = Project.objects.get_or_create(
                    code=code, defaults={'name': name, 'public': public}
                )
                if was_created:
                    created += 1
                elif project.name != name or project.public != public:
                    project.name = name
                    project.public = public
                    project.save(update_fields=['name', 'public'])
                    updated += 1
                else:
                    unchanged += 1

                # reconcile members by username - only existing local users can be members;
                # this command doesn't create Django user accounts
                users = list(User.objects.filter(username__in=usernames))
                found_usernames = {u.username for u in users}
                unknown_usernames.update(set(usernames) - found_usernames)

                current_member_ids = set(project.users.values_list('pk', flat=True))
                new_member_ids = {u.pk for u in users}
                members_added += len(new_member_ids - current_member_ids)
                members_removed += len(current_member_ids - new_member_ids)

                project.users.set(users)

            # delete projects that no longer exist on the portal
            deleted, _ = Project.objects.exclude(code__in=seen_codes).delete()

        log.info(
            'Synced projects: %d created, %d updated, %d unchanged, %d deleted; '
            '%d memberships added, %d removed.',
            created, updated, unchanged, deleted, members_added, members_removed
        )
        self.stdout.write(
            'Synced projects: %d created, %d updated, %d unchanged, %d deleted; '
            '%d memberships added, %d removed.'
            % (created, updated, unchanged, deleted, members_added, members_removed)
        )
        if unknown_usernames:
            log.warning(
                'Portal reported %d project member(s) with no matching local user: %s',
                len(unknown_usernames), ', '.join(sorted(unknown_usernames))
            )
            self.stdout.write(
                self.style.WARNING(
                    'Skipped %d unknown username(s) (no matching local user): %s'
                    % (len(unknown_usernames), ', '.join(sorted(unknown_usernames)))
                )
            )
