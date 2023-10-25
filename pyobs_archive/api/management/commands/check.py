import os

from django.core.management.base import BaseCommand

from pyobs_archive.api.models import Frame
from pyobs_archive import settings


class Command(BaseCommand):
    help = 'Check files and database'

    def add_arguments(self, parser):
        parser.add_argument('-d', '--dry', action='store_true', help='Dry run')

    def handle(self, *args, **options):
        for frame in Frame.objects.all():
            # check file
            if not frame.check_file():
                print(f'{frame.basename} missing.')
