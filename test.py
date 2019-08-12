import requests
import glob

s = requests.session()
r = s.get('http://127.0.0.1:8000/')

#filename = '/opt/pyobs/monets1m2-kb01-20190811-0005-e00.fits'
for filename in glob.glob('/opt/pyobs/temp/*'):
    print(filename)
    files = {'image': open(filename, 'rb')}
    url = 'http://127.0.0.1:8000/images/'
    r = s.post(url, data={'csrfmiddlewaretoken': s.cookies['csrftoken']}, files=files)
    print(r.status_code)
