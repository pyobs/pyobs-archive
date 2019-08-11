import requests

s = requests.session()

r = s.get('http://127.0.0.1:8000/')
print(s.cookies)
print(s.cookies['csrftoken'])


filename = '/data/astro/temp/monet/data/monets/20180325/science20180325S-0014EXP0163.fits'
files = {'image': open(filename, 'rb')}
url = 'http://127.0.0.1:8000/images/'
r = s.post(url, data={'csrfmiddlewaretoken': s.cookies['csrftoken']}, files=files)

print(r.text)
