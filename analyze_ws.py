import re

with open('miniapp.js', 'r', encoding='utf-8') as f:
    content = f.read()

# jm fonksiyonunu bul (window.connect = jm)
# Bunu yapmak icin jm'nin tanimlandigini yerini bul
print("=== connect (jm) fonksiyonu ===")
# jm fonksiyonu WebSocket URL'ini olusturur
jm_matches = list(re.finditer(r'function jm', content))
for m in jm_matches:
    ctx = content[m.start():m.start()+1500]
    print(ctx)
    
# Alternatif: async function jm
async_jm = list(re.finditer(r'async function jm', content))
for m in async_jm:
    ctx = content[m.start():m.start()+1500]
    print(ctx)

# WS URL olusturma - initData nereden ekleniyor?
print("\n\n=== URL olusturma (initData + WS) ===")
for m in re.finditer(r'initData[^;]{0,50}ws\.|ws\.[^;]{0,50}initData', content):
    ctx = content[max(0,m.start()-200):m.start()+400]
    print(ctx[:600])
    print("---")

# "welcome" mesaji - sunucu basa ne gonderiyor?
print("\n\n=== handleWelcome (Jm) - sunucunun ilk mesaji ===")
for m in re.finditer(r'function Jm|handleWelcome', content):
    ctx = content[m.start():m.start()+600]
    print(ctx)
    print("---")

# ws URL'i nasil olusturuluyor
print("\n\n=== WebSocket URL olusturma ===")
for m in re.finditer(r'wss://ws\.[^"\']{5,100}', content):
    ctx = content[max(0,m.start()-300):m.start()+400]
    print(ctx[:700])
    print("---")
