import json
import uuid
import psycopg2
from psycopg2 import sql

class PostgreSQLConverterEngine:
    def __init__(self, vt_ayarlari):
        # veritabanına baglanmak için gerekli bilgileri şifre kullanıcı vb saklıyoruz
        self.vt_ayarlari = vt_ayarlari
        # oluşturacağımız tablo taslaklarını ve sütun tiplerini burada tutuyoruz
        self.veritabani_semasi = {}
        # eklenecek olan verileri ve tablolari islem sonuna kadar liste olarak biriktiriyoruz
        self.eklenecek_kayitlar = []

    def sql_tipi_belirle(self, deger):
        # python dan gelen veri tipini postresql de karsılık gelen veritipini belirliyoruz
        if isinstance(deger, bool):
            return "BOOLEAN"
        elif isinstance(deger, int):
            return "INTEGER"
        elif isinstance(deger, float):
            return "NUMERIC"
        else:
            return "TEXT"

    def sozlugu_duzlestir(self, sozluk, ust_anahtar='', ayrac='_'):
        # ic içe geçmiş json objelerini SQL tablolarında tek bir düzlemde sütunlar halinde tutabilmek için düzlestiriyoruz
        ogeler = []
        for anahtar, deger in sozluk.items():
            # sql de harf cakısması olmaması için anahtarları kucuk harf yapıyoruz
            kucuk_anahtar = str(anahtar).lower()
            
            yeni_anahtar = f"{ust_anahtar}{ayrac}{kucuk_anahtar}" if ust_anahtar else kucuk_anahtar
            if isinstance(deger, dict):
                ogeler.extend(self.sozlugu_duzlestir(deger, yeni_anahtar, ayrac=ayrac).items())
            else:
                ogeler.append((yeni_anahtar, deger))
        return dict(ogeler)
    
    def reset_database(self):
        # veritabanını sifirlıyoruz ki bi sonraki test de cakışma olmasın
        self.veritabani_semasi = {}
        self.eklenecek_kayitlar = []

        baglanti = psycopg2.connect(**self.vt_ayarlari)
        imlec = baglanti.cursor()
        try:
            print("\nSİSTEM SIFIRLANIYOR (DROP CASCADE)")
            # veritabanındaki butun tabloları temizliyoruz
            imlec.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            baglanti.commit()
            print("-> Eski tablolar tamamen silindi Veritabanı yeni JSON için tertemiz.")
        except Exception as hata:
            baglanti.rollback()
            print(f"Hata: {hata}")
        finally:
            imlec.close()
            baglanti.close()

    def process_data(self, tablo_adi, veri_sozlugu, ust_id=None, yabanci_anahtar_adi=None):
        # gelen json dosyasının analiz aşaması
        
        # eğer veri listeyse içindeki elemanları tek tek ayıklayıp rekursif olarak işleme alıyoruz
        if isinstance(veri_sozlugu, list):
            for eleman in veri_sozlugu:
                self.process_data(tablo_adi, eleman, ust_id, yabanci_anahtar_adi)
            return # döngü bitince fonksiyondan cıkıyoruz 

        duz_veri = self.sozlugu_duzlestir(veri_sozlugu)
        
        # 2NF kuralı geregi bu satıra (o anki json da okunan nesne) özel primary key atıyoruz
        guncel_id = str(uuid.uuid4())
        
        # eğer tablo daha önce şemamıza eklenmemişse  id_pk sütunuyla beraber ilk kaydını oluşturuyoruz
        if tablo_adi not in self.veritabani_semasi:
            self.veritabani_semasi[tablo_adi] = {
                "sutunlar": {"id_pk": "VARCHAR(50)"}, 
                "yabanci_anahtarlar": []
            }
            
        # bu satıra eklenecek olan verileri geçici olarak bir sözlükte topluyoruz
        satir_verisi = {"id_pk": guncel_id}
        
        # eğer veri alt tabloya aitse üst tablosunun foreign keyini de sütün olarak ekliyoruz
        if ust_id and yabanci_anahtar_adi:
            self.veritabani_semasi[tablo_adi]["sutunlar"][yabanci_anahtar_adi] = "VARCHAR(50)"
            
            bulunan_ust_tablo = yabanci_anahtar_adi.split('_id')[0]
            ya_iliskisi = {"ust_tablo": bulunan_ust_tablo, "ya_sutunu": yabanci_anahtar_adi}
            
            if ya_iliskisi not in self.veritabani_semasi[tablo_adi]["yabanci_anahtarlar"]:
                self.veritabani_semasi[tablo_adi]["yabanci_anahtarlar"].append(ya_iliskisi)
                
            satir_verisi[yabanci_anahtar_adi] = ust_id

        # duzleştirilmiş verideki alanları tarıyoruz
        for anahtar, deger in duz_veri.items():
            # 1NF kural geregi eger deger listeyse tek bi satıra sıkıştırmak yerine bi alt tablo olusturyoruz
            if isinstance(deger, list):
                alt_tablo_adi = f"{tablo_adi}_{anahtar}"
                ya_sutun_adi = f"{tablo_adi}_id"
                
                for eleman in deger:
                    if not isinstance(eleman, dict):
                        eleman = {"deger": eleman}
                    self.process_data(alt_tablo_adi, eleman, ust_id=guncel_id, yabanci_anahtar_adi=ya_sutun_adi)
            
            # Eğer değer normal sayı metin vs ise sql e uyarlayıp tablomuza sütun olarak ekliyoruz
            else:
                sql_tipi = self.sql_tipi_belirle(deger)
                self.veritabani_semasi[tablo_adi]["sutunlar"][anahtar] = sql_tipi
                satir_verisi[anahtar] = deger
                
        # satır verisini sonraki sorgularda kullanmak için hafızaya alıyoruz 
        self.eklenecek_kayitlar.append((tablo_adi, satir_verisi))
        return guncel_id
    

    def execute_migration(self):
        # PostgreSQL e otonom veri aktarma
        baglanti = psycopg2.connect(**self.vt_ayarlari)
        imlec = baglanti.cursor()
        
        try:
            print("\n" + "="*50)
            print("1. AŞAMA: DİNAMİK TABLOLARIN OLUŞTURULMASI")
            
            for tablo_adi, detaylar in self.veritabani_semasi.items():
                sutun_tanimlari = []
                for sutun_adi, sutun_tipi in detaylar["sutunlar"].items():
                    if sutun_adi == "id_pk":
                        sutun_tanimlari.append("id_pk VARCHAR(50) PRIMARY KEY")
                    else:
                        sutun_tanimlari.append(f"{sutun_adi} {sutun_tipi}")
                
                # CREATE TABLE sorgusu
                olusturma_sorgusu = f"CREATE TABLE IF NOT EXISTS {tablo_adi} (\n    " + ",\n    ".join(sutun_tanimlari) + "\n);"
                
                # Sorguyu çalıştırmadan önce terminale basma
                print(f"\n[SİSTEM SQL YAZIYOR - CREATE]:\n{olusturma_sorgusu}")
                imlec.execute(olusturma_sorgusu)
            
            print("\n" + "="*50)
            print("2. AŞAMA: VERİLERİN İLİŞKİSEL AKTARIMI (INSERT)")
            print("\n" + "="*50)
            
            for tablo_adi, satir_verisi in reversed(self.eklenecek_kayitlar):
                sutunlar = satir_verisi.keys()
                degerler = list(satir_verisi.values())
                
                ekleme_sorgusu = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(tablo_adi),
                    sql.SQL(', ').join(map(sql.Identifier, sutunlar)),
                    sql.SQL(', ').join(sql.Placeholder() * len(degerler))
                )
                
                # sql sorgusunu ekranda (logda) görebilmek için metne çeviriyoruz
                ham_sql = ekleme_sorgusu.as_string(baglanti)
                print(f"[SİSTEM SQL YAZIYOR - INSERT]: {ham_sql} \n  --> EKLENEN DEĞERLER: {degerler}\n")
                imlec.execute(ekleme_sorgusu, degerler)

            print("\n" + "="*50)
            print("3. AŞAMA: FOREIGN KEY (YABANCI ANAHTAR) BAĞLANTILARI")
            
            for tablo_adi, detaylar in self.veritabani_semasi.items():
                for ya in detaylar["yabanci_anahtarlar"]:
                    # ALTER TABLE sorgusu
                    degistirme_sorgusu = f"ALTER TABLE {tablo_adi} ADD CONSTRAINT fk_{tablo_adi}_{ya['ust_tablo']} FOREIGN KEY ({ya['ya_sutunu']}) REFERENCES {ya['ust_tablo']}(id_pk) ON DELETE CASCADE;"
                    
                    # Sorguyu terminale basma
                    print(f"\n[SİSTEM SQL YAZIYOR - ALTER]:\n{degistirme_sorgusu}")
                    
                    # Hata almamak için güvenli blok içinde çalıştır
                    guvenli_degistirme_sorgusu = f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_{tablo_adi}_{ya['ust_tablo']}') THEN
                            {degistirme_sorgusu}
                        END IF;
                    END $$;
                    """
                    imlec.execute(guvenli_degistirme_sorgusu)
            
            baglanti.commit()
            print("\n[MİGRASYON BAŞARILI] NoSQL verisi PostgreSQL ilişkisel yapısına başarıyla dönüştürüldü")
            
        except Exception as hata:
            baglanti.rollback()
            raise Exception(f"Veritabanı aktarım hatası: {hata}")
        finally:
            imlec.close()
            baglanti.close()

# motoru calıstırma ve test etme
if __name__ == "__main__":
    yerel_vt_ayarlari = {
        "dbname": "prolab_db",
        "user": "postgres",
        "password": "Avdatek5003", 
        "host": "localhost",
        "port": "5432"
    }
    
    motor = PostgreSQLConverterEngine(vt_ayarlari=yerel_vt_ayarlari)
    
    # db temizliyoruz
    motor.reset_database()
    
    print("\n2. PostgreSQL Veritabanı Geçişi (Migration) Başlatılıyor...")
    # toplanan veriyi sql tablolarına aktarıyoruz
    motor.execute_migration()