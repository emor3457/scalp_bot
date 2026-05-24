import urllib.request, re, json

js_url = 'https://7k2v9x1r0z8t4m3n5p7w.com/assets/index-w4CHQtSW.js'
print('JS dosyasi indiriliyor...')

req = urllib.request.Request(js_url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://7k2v9x1r0z8t4m3n5p7w.com/',
})

with urllib.request.urlopen(req, timeout=15) as r:
    content = r.read().decode('utf-8')
    print(f'JS boyutu: {len(content)} karakter')

patterns = [
    r'["\'](/api/[^"\'\\s]+)',
    r'(wss?://[^"\'\\s\\)]+)',
    r'(https?://[^"\'\\s]*api[^"\'\\s]*)',
    r'baseURL["\'\\s:]+["\'](https?://[^"\']+)',
    r'["\'](/depth[^"\'\\s]*)',
    r'["\'](/trade[^"\'\\s]*)',
    r'["\'](/stock[^"\'\\s]*)',
    r'["\'](/market[^"\'\\s]*)',
    r'["\'](/quote[^"\'\\s]*)',
    r'["\'](/bist[^"\'\\s]*)',
    r'["\'](/v[0-9]/[^"\'\\s]+)',
]

found = set()
for pattern in patterns:
    matches = re.findall(pattern, content)
    for m in matches:
        if 3 < len(m) < 120:
            found.add(m)

print(f'\nBulunan endpoint/URL adaylari ({len(found)} adet):')
for item in sorted(found):
    print(f'  {item}')

with open('miniapp.js', 'w', encoding='utf-8') as f:
    f.write(content)
print('\nJS dosyasi miniapp.js olarak kaydedildi.')

# Ilk 5000 karakteri yazdir - ortam degiskenlerine veya config'e bak
print('\n--- JS BASLANGICI (ilk 2000 karakter) ---')
print(content[:2000])
