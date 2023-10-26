import os

from django.core.management.base import BaseCommand

from pyobs_archive.api.models import Frame
from pyobs_archive import settings


class Command(BaseCommand):
    help = 'Check files and database'

    def add_arguments(self, parser):
        parser.add_argument('-d', '--dry', action='store_true', help='Dry run')

    def handle(self, *args, **options):
        for i, frame in enumerate(Frame.objects.all()):
            # check file
            if frame.check_file():
                # file ok
                if i % 100 == 0:
                    # print a point every 100 entries
                    print('.', end='', flush=True)
            else:
                # file not ok, dry run?
                if 'dry' in options and options["dry"]:
                    print(f'\n{frame.basename} missing, deleting database entry.')
                else:
                    print(f'{frame.basename} missing.')
