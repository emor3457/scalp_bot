import os
import sqlite3

DB_PATH = "bot.db"

def reset_database():
    print("[*] Veritabanı sıfırlama işlemi başlatılıyor...")
    
    # Veritabanı dosyasını silmeyi dene, kilitliyse tabloları drop et
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"[+] Eski veritabanı dosyası ({DB_PATH}) silindi.")
        except Exception as e:
            print(f"[-] Veritabanı dosyası silinemedi (kilitli olabilir). Tablolar temizleniyor... Hata: {str(e)}")
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS signals")
                cursor.execute("DROP TABLE IF EXISTS trades")
                cursor.execute("DROP TABLE IF EXISTS portfolio")
                conn.commit()
                conn.close()
                print("[+] Tüm eski tablolar başarıyla drop edildi.")
            except Exception as ex:
                print(f"[-] Tablolar drop edilirken hata oluştu: {str(ex)}")
                return
    else:
        print("[*] Mevcut bir veritabanı dosyası bulunamadı, yeni bir tane oluşturulacak.")

    # database.py modülündeki init_db fonksiyonunu çağırarak sıfırdan tabloları kur ve 500.000 TL ekle
    try:
        from database import init_db
        init_db()
        print("[+] Yeni veritabanı şeması başarıyla kuruldu.")
        print("[+] Başlangıç bakiyesi olarak 500,000.00 TL (TRY) yüklendi ve portföy sıfırlandı.")
        print("[+] Sıfırlama işlemi başarıyla tamamlandı!")
    except Exception as e:
        print(f"[-] Veritabanı başlatılırken hata oluştu: {str(e)}")

if __name__ == "__main__":
    reset_database()
