import os

from django.core.management.base import BaseCommand

from pyobs_archive.api.models import Frame
from pyobs_archive import settings


class Command(BaseCommand):
    help = 'Ingest images'

    def add_arguments(self, parser):
        parser.add_argument('files', type=str, nargs='+', help='Names of files to delete')

    def handle(self, *args, files: list = None, **options):
        to_delete = []
        for filename in files:
            frames = Frame.objects.filter(basename=filename)
            if len(frames) > 0:
                to_delete.append(frames)

        if not to_delete:
            return

        print("Images to delete:")
        for d in to_delete:
            print("  - " + d.basename)
        reply = None
        while reply not in 'yYnN':
            reply = input("Delete files? [yn]")

        if reply not in 'yY':
            return

        for d in to_delete:
            # get filename
            root = settings.ARCHIVE_ROOT
            filename = os.path.join(root, frame.path, frame.basename + '.fits.fz')

            # delete file
            os.remove(filename)

            # delete db entry
            d.delete()

