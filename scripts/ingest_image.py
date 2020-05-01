import argparse
from typing import List
import os
from urllib.parse import urljoin
import sys
import requests


def ingest_image(filename: str, url: str, token: str):
    # create session and define headers
    session = requests.session()
    headers = {'Authorization': 'Token ' + token}

    # do some initial GET request for getting the csrftoken
    session.get(url, headers=headers)

    # open file
    img = open(filename, 'rb')

    # remove path
    filename = os.path.basename(filename)

    # send file
    print("Ingesting file %s..." % filename)
    r = session.post(
        urljoin(url, 'frames/create/'),
        data={'csrfmiddlewaretoken': session.cookies['csrftoken']},
        files={os.path.basename(filename): img},
        headers=headers
    )

    # success, if status code is 200
    if r.status_code != 200:
        print('Cannot write file, received status_code %d: %s' % (r.status_code, r.content))
        sys.exit(1)

    # check json
    json = r.json()
    if 'created' not in json or json['created'] == 0:
        if 'errors' in json:
            print('Could not create file in archive: ' + str(json['errors']))
            sys.exit(1)
        else:
            print('Could not create file in archive.')
            sys.exit(1)

    # success
    print('Done')
    sys.exit(0)


if __name__ == '__main__':
    # define command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', type=str, help='Name of file to ingest into archive')
    parser.add_argument('-u', '--url', type=str, help='URL of archive', default=os.environ.get('ARCHIVE_URL', None))
    parser.add_argument('-t', '--token', type=str, help='Auth token for archive',
                        default=os.environ.get('ARCHIVE_TOKEN', None))

    # parse command line arguments
    args = parser.parse_args()

    # call main
    ingest_image(**vars(args))
