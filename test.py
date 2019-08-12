import requests
import glob

headers = {
    'Authorization': 'Token 7ab68d7e7cecf2273222970329a4f266aa0c299f'
}

s = requests.session()
r = s.get('http://127.0.0.1:8000/', headers=headers)

#filename = '/opt/pyobs/monets1m2-kb01-20190811-0005-e00.fits'
for filename in glob.glob('/opt/pyobs/temp/*'):
    print(filename)
    files = {'image': open(filename, 'rb')}
    url = 'http://127.0.0.1:8000/create/'
    r = s.post(url, data={'csrfmiddlewaretoken': s.cookies['csrftoken']}, files=files, headers=headers)
    print(r.status_code)
