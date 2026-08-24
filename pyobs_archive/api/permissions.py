"""Project-based access control for Frame objects.

See specs/plans/2026-08-20-archive-project-access-control.md, section 4. All checks here are
gated by callers on `settings.PROJECT_ACCESS_CONTROL` (see pyobs_archive/api/views.py) - this
module itself doesn't consult the setting, so it stays simple to unit test.
"""

from django.db.models import Q

from pyobs_archive.api.models import Project


def accessible_projects(user):
    """Project codes `user` may see frames of.

    Returns:
        None for superusers/staff, meaning "everything" (D6). Otherwise the set of project
        codes that are either public or that `user` is a member of.
    """
    if not getattr(user, 'is_authenticated', False):
        return set()

    if user.is_superuser or user.is_staff:
        return None

    public = Project.objects.filter(public=True).values_list('code', flat=True)
    member = Project.objects.filter(users=user).values_list('code', flat=True)
    return set(public) | set(member)


def can_access_frame(user, frame):
    """Whether `user` may see `frame`.

    Superusers/staff always can (D6). Otherwise a frame with no PROJECT association is
    superuser-only (D5, fail closed), and any other frame requires its PROJECT to be in
    `accessible_projects(user)`.
    """
    if not getattr(user, 'is_authenticated', False):
        return False

    if user.is_superuser or user.is_staff:
        return True

    projects = accessible_projects(user)
    return frame.PROJECT is not None and frame.PROJECT in projects


def frame_access_q(user):
    """Q object restricting a Frame queryset to what `user` may see.

    Returns an unfiltered Q() for superusers/staff (consistent with accessible_projects()'s
    None="everything"), so callers don't need a separate is_superuser/is_staff branch.
    """
    projects = accessible_projects(user)
    if projects is None:
        return Q()
    return Q(PROJECT__in=projects)


def filter_accessible_frames(user, frames):
    """Filter an already-fetched iterable of Frame objects down to what `user` may access.

    Equivalent to `[f for f in frames if can_access_frame(user, f)]`, but computes
    `accessible_projects(user)` once up front instead of once per frame - use this (rather than
    calling `can_access_frame` in a loop) when checking several frames for the same user, e.g. a
    frame's related-frames list (D10), to avoid an avoidable query per frame.
    """
    projects = accessible_projects(user)
    if projects is None:
        return list(frames)
    return [f for f in frames if f.PROJECT is not None and f.PROJECT in projects]
