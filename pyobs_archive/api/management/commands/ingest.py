from django.core.management.base import BaseCommand

from pyobs_archive.api.models import Frame


class Command(BaseCommand):
    help = 'Ingest images'

    def add_arguments(self, parser):
        parser.add_argument('files', type=str, nargs='+', help='Names of files to ingest')

    def handle(self, *args, files: list = None, **options):
        for filename in files:
            Frame.ingest(filename)
