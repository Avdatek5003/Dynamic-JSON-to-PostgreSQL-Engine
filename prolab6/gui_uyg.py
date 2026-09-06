import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import psycopg2
import re
import sys 

# diğer class taki dönüşüm motorumuzu arayüze dahil ediyoruz
from parser_engine import PostgreSQLConverterEngine

class CiktiYonlendirici:
    def __init__(self, metin_kutusu):
        self.metin_kutusu = metin_kutusu

    def write(self, yazi):
        self.metin_kutusu.insert(tk.END, yazi)
        self.metin_kutusu.see(tk.END) 

    def flush(self):
        pass

class ProlabArayuz:
    def __init__(self, ana_pencere):
        self.ana_pencere = ana_pencere
        self.ana_pencere.title("NoSQL to SQL Dynamic Converter Engine")
        #pencere boyutu
        self.ana_pencere.geometry("1300x900") 
        
        #arayüz şekillendirme
        self.stil = ttk.Style(self.ana_pencere)
        self.stil.theme_use("clam") 
        
        # buton ayarları
        self.stil.configure("TButton", font=("Segoe UI", 10, "bold"), background="#0078D7", foreground="white", padding=6)
        self.stil.map("TButton", background=[('active', '#005A9E')]) 
        
        #Frame ve label stilleri
        self.stil.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"), foreground="#0078D7")
        self.stil.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#E1E1E1", foreground="#333333")
        self.stil.configure("Treeview", font=("Segoe UI", 10), rowheight=25)
        
        #veritabanı bağlantı ayarlari
        self.vt_ayarlari = {
            "dbname": "prolab_db",
            "user": "postgres",
            "password": "Avdatek5003", 
            "host": "localhost",
            "port": "5432"
        }
        self.motor = PostgreSQLConverterEngine(self.vt_ayarlari)
        self.yuklenen_json_verisi = None
        self.guncel_tablo_adi = ""
        
        self.arayuzu_kur()

    def arayuzu_kur(self):
        # arayüzü 2ye boluyoruz(sql nosql)
        ana_panel = ttk.PanedWindow(self.ana_pencere, orient=tk.HORIZONTAL)
        ana_panel.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

         # sol panel json yukleme 
        sol_cerceve = ttk.LabelFrame(ana_panel, text="NoSQL (JSON) Yönetimi ve Ağaç Yapısı")
        ana_panel.add(sol_cerceve, weight=1)

        # json secme sıfırlama dönüstürme butonları
        buton_cercevesi = ttk.Frame(sol_cerceve)
        buton_cercevesi.pack(fill=tk.X, pady=10, padx=5)
        
        ttk.Button(buton_cercevesi, text="1. JSON Dosyası Seç", command=self.dosya_yukle).pack(side=tk.LEFT, padx=5)
        ttk.Button(buton_cercevesi, text="2. Sistemi Sıfırla (DROP)", command=self.veritabanini_sifirla).pack(side=tk.LEFT, padx=5)
        ttk.Button(buton_cercevesi, text="3. SQL'e Dönüştür", command=self.donusumu_baslat).pack(side=tk.LEFT, padx=5)
        # yuklenen json verisini gösterecegimiz alan
        self.json_agaci = ttk.Treeview(sol_cerceve)
        self.json_agaci.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.json_agaci.heading("#0", text="JSON Hiyerarşisi", anchor="w")

        # sağ panel sonuc tablosu
        sag_cerceve = ttk.LabelFrame(ana_panel, text="SQL Sorgu Terminali ve DataGrid")
        ana_panel.add(sag_cerceve, weight=1)
        # oluturulan tabloları listeleyeceğimiz açılır menu
        tablo_cercevesi = ttk.Frame(sag_cerceve)
        tablo_cercevesi.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(tablo_cercevesi, text="Mevcut Tablolar:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.tablo_secici = ttk.Combobox(tablo_cercevesi, state="readonly", font=("Segoe UI", 10))
        self.tablo_secici.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.tablo_secici.bind("<<ComboboxSelected>>", self.tablo_secildiginde)
        
        ttk.Button(tablo_cercevesi, text="Tabloları Yenile", command=self.tablolari_yenile).pack(side=tk.LEFT)
        # elle veya sistemin SQL sorgularını yazıp çalıştıracağımız metin kutusu
        self.sql_metni = tk.Text(sag_cerceve, height=5, font=("Consolas", 11), bg="#F4F4F4")
        self.sql_metni.pack(fill=tk.X, padx=5, pady=5)
        self.sql_metni.insert(tk.END, "-- İşlem sonrası oluşan tabloları yukarıdan seçebilir\n-- veya buraya manuel sorgu yazabilirsiniz.\n")

        #Butonu sağa yaslama
        ttk.Button(sag_cerceve, text="Sorguyu Çalıştır (Execute) ▶", command=self.sorguyu_calistir).pack(pady=5, anchor="e", padx=5)
        # sorgu sonuçlarının listeleneceği ızgara yapısı
        self.sonuc_agaci = ttk.Treeview(sag_cerceve, show="headings")
        self.sonuc_agaci.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        # dikey kaydırma cubugu
        kaydirma_cubugu = ttk.Scrollbar(sag_cerceve, orient=tk.VERTICAL, command=self.sonuc_agaci.yview)
        self.sonuc_agaci.configure(yscroll=kaydirma_cubugu.set)
        kaydirma_cubugu.pack(side=tk.RIGHT, fill=tk.Y)

        #Alt panel
        log_cercevesi = ttk.LabelFrame(self.ana_pencere, text="Sistem Logları ve Otonom SQL Çıktıları")
        log_cercevesi.pack(fill=tk.X, padx=10, pady=(0, 10))

        #Terminalin yüksekliği
        self.log_konsolu = tk.Text(log_cercevesi, height=14, bg="#1E1E1E", fg="#00FF00", font=("Consolas", 11, "bold"))
        self.log_konsolu.pack(fill=tk.X, padx=5, pady=5)
        
        log_kaydirma = ttk.Scrollbar(log_cercevesi, orient=tk.VERTICAL, command=self.log_konsolu.yview)
        self.log_konsolu.configure(yscroll=log_kaydirma.set)
        log_kaydirma.pack(side=tk.RIGHT, fill=tk.Y)

        sys.stdout = CiktiYonlendirici(self.log_konsolu)
        
        # Arayüz acıldıgında veritabanındaki tabloları listeye ekliyoruz
        self.tablolari_yenile()

    #Bağlantı fonksiyonları

    def dosya_yukle(self):
        # seçtiğimiz json dosyasını belleğe okuyoruz
        dosya_yolu = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if dosya_yolu:
            with open(dosya_yolu, "r", encoding="utf-8") as f:
                self.yuklenen_json_verisi = json.load(f)
            # dosya adından hareketle ana tablo ismi üretiyoruz
            temel_ad = os.path.basename(dosya_yolu)
            ham_ad = os.path.splitext(temel_ad)[0].lower()
            self.guncel_tablo_adi = re.sub(r'\W+', '_', ham_ad)
            self.json_agaci.delete(*self.json_agaci.get_children())
            self.agaci_doldur("", self.guncel_tablo_adi, self.yuklenen_json_verisi)
            
            print(f"[*] Bilgi: '{temel_ad}' dosyası sisteme yüklendi.")
            messagebox.showinfo("Başarılı", f"'{temel_ad}' başarıyla yüklendi!")

    def agaci_doldur(self, ebeveyn, anahtar, deger):
        # jsondaki nesneleri ve listeleri rekursif olarak arayüzüne yerleştiriyoruz
        dugum = self.json_agaci.insert(ebeveyn, "end", text=str(anahtar))
        if isinstance(deger, dict):
            for a, d in deger.items():
                self.agaci_doldur(dugum, a, d)
        elif isinstance(deger, list):
            for i, eleman in enumerate(deger):
                self.agaci_doldur(dugum, f"[{i}]", eleman)
        else:
            self.json_agaci.insert(dugum, "end", text=f": {deger}")

    def veritabanini_sifirla(self):
        # butona bastıgımızda reset fonksiyonu çağrılıp tabloları siliyoruz
        try:
            self.motor.reset_database()
            messagebox.showinfo("Sistem Sıfırlandı", "Veritabanındaki tüm tablolar (DROP CASCADE) başarıyla temizlendi!")
            self.tablolari_yenile() 
        except Exception as hata:
            messagebox.showerror("Hata", f"Sıfırlama başarısız: {hata}")

    def donusumu_baslat(self):
        # json u sql e donusturmeye baslıyoruz
        if not self.yuklenen_json_verisi:
            messagebox.showwarning("Uyarı", "Lütfen önce bir JSON dosyası seçin!")
            return
        
        try:
            # sql şemasını hazırlıyoruz
            self.motor.process_data(self.guncel_tablo_adi, self.yuklenen_json_verisi)
            # Üretilen sanal şemayı postgre tablolarına yazıyoruz
            self.motor.execute_migration()
            messagebox.showinfo("Migrasyon Başarılı", "JSON verisi otonom olarak SQL tablolarına dönüştürüldü ve veritabanına aktarıldı!")
            self.tablolari_yenile()
        except Exception as hata:
            messagebox.showerror("Migrasyon Hatası", str(hata))

    def tablolari_yenile(self):
        try:
            baglanti = psycopg2.connect(**self.vt_ayarlari)
            imlec = baglanti.cursor()
            imlec.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tablolar = [satir[0] for satir in imlec.fetchall()]
            # cekilen tablo isimlerini listeye aktarıyoruz
            self.tablo_secici['values'] = tablolar
            if not tablolar:
                self.tablo_secici.set("Tablo bulunamadı...")
            else:
                self.tablo_secici.set("İncelemek için bir tablo seçin...")
                
        except Exception as hata:
            print(f"Tablolar çekilemedi: {hata}")
        finally:
            if 'imlec' in locals(): imlec.close()
            if 'baglanti' in locals(): baglanti.close()

    def tablo_secildiginde(self, olay):
        #  tablo seçtiğimizde select sorgusunu otomatik üretip çalıştırıyoruz
        secilen_tablo = self.tablo_secici.get()
        if secilen_tablo and secilen_tablo not in ["Tablo bulunamadı...", "İncelemek için bir tablo seçin..."]:
           #  eski sorguyu temizleyip yeni sorguyu yapıştırıyoruz 
            self.sql_metni.delete("1.0", tk.END)
            self.sql_metni.insert(tk.END, f"SELECT * FROM {secilen_tablo};")
            self.sorguyu_calistir()

    def sorguyu_calistir(self):
        # metin kutusundaki sql sorgusunu çalıştırıp, dönen verileri arayüzde gösteriyoruz
        sorgu = self.sql_metni.get("1.0", tk.END).strip()
        if not sorgu:
            return

        try:
            baglanti = psycopg2.connect(**self.vt_ayarlari)
            imlec = baglanti.cursor()
            imlec.execute(sorgu)
            #  okuma işlemi yapıldıysa sütun isimlerini ve satırları çekiyoruz
            if sorgu.lower().startswith("select"):
                satirlar = imlec.fetchall()
                sutun_isimleri = [aciklama[0] for aciklama in imlec.description]
                self.sonuc_agaci.delete(*self.sonuc_agaci.get_children())
                self.sonuc_agaci["columns"] = sutun_isimleri
                # Tablonun sütun isimlerini sql den dönen isimlerle ayarlıyoruz
                for sutun in sutun_isimleri:
                    self.sonuc_agaci.heading(sutun, text=sutun)
                    self.sonuc_agaci.column(sutun, width=100)
                # Her bir kaydı sırayla tablo satırı olarak ekliyoruz
                for satir in satirlar:
                    self.sonuc_agaci.insert("", tk.END, values=satir)
                
                print(f"\n[SQL Yürütüldü] {sorgu}")
            else:
                baglanti.commit()
                messagebox.showinfo("Başarılı", "Sorgu başarıyla çalıştırıldı (Sonuç döndürmeyen işlem).")
                self.tablolari_yenile() 
                print(f"\n[SQL Yürütüldü] {sorgu}")
                
        except Exception as hata:
            messagebox.showerror("SQL Hatası", str(hata))
            print(f"\n[HATA] {str(hata)}")
        finally:
            if 'imlec' in locals(): imlec.close()
            if 'baglanti' in locals(): baglanti.close()

if __name__ == "__main__":
    kok_pencere = tk.Tk()
    uygulama = ProlabArayuz(kok_pencere)
    kok_pencere.mainloop()