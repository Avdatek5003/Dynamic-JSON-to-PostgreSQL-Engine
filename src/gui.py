import json
import os
import sys
import tkinter as tk

from tkinter import (
    filedialog,
    messagebox,
    ttk
)

import psycopg2

from psycopg2 import sql

from config import get_database_config
from parser_engine import PostgreSQLConverterEngine


class CiktiYonlendirici:

    def __init__(
        self,
        metin_kutusu
    ):
        self.metin_kutusu = (
            metin_kutusu
        )

    def write(
        self,
        yazi
    ):

        if not yazi:
            return

        self.metin_kutusu.insert(
            tk.END,
            yazi
        )

        self.metin_kutusu.see(
            tk.END
        )

        self.metin_kutusu.update_idletasks()

    def flush(self):
        pass


class ProlabArayuz:

    def __init__(
        self,
        ana_pencere
    ):

        self.ana_pencere = (
            ana_pencere
        )

        self.ana_pencere.title(
            "NoSQL to SQL Dynamic Converter Engine"
        )

        self.ana_pencere.geometry(
            "1300x900"
        )

        # STYLE
        self.stil = ttk.Style(
            self.ana_pencere
        )

        self.stil.theme_use(
            "clam"
        )

        self.stil.configure(
            "TButton",
            font=(
                "Segoe UI",
                10,
                "bold"
            ),
            background="#0078D7",
            foreground="white",
            padding=6
        )

        self.stil.map(
            "TButton",
            background=[
                (
                    "active",
                    "#005A9E"
                )
            ]
        )

        self.stil.configure(
            "TLabelframe.Label",
            font=(
                "Segoe UI",
                11,
                "bold"
            ),
            foreground="#0078D7"
        )

        self.stil.configure(
            "Treeview.Heading",
            font=(
                "Segoe UI",
                10,
                "bold"
            ),
            background="#E1E1E1",
            foreground="#333333"
        )

        self.stil.configure(
            "Treeview",
            font=(
                "Segoe UI",
                10
            ),
            rowheight=25
        )
        # DATABASE
        self.vt_ayarlari = (
            get_database_config()
        )

        self.motor = (
            PostgreSQLConverterEngine(
                self.vt_ayarlari
            )
        )

        self.yuklenen_json_verisi = None
        self.guncel_tablo_adi = ""

        self.arayuzu_kur()
    # GUI
    def arayuzu_kur(self):

        ana_panel = ttk.PanedWindow(
            self.ana_pencere,
            orient=tk.HORIZONTAL
        )

        ana_panel.pack(
            fill=tk.BOTH,
            expand=True,
            padx=10,
            pady=(
                10,
                5
            )
        )
        # LEFT PANEL
        sol_cerceve = ttk.LabelFrame(
            ana_panel,
            text=(
                "NoSQL (JSON) Yönetimi "
                "ve Ağaç Yapısı"
            )
        )

        ana_panel.add(
            sol_cerceve,
            weight=1
        )

        buton_cercevesi = ttk.Frame(
            sol_cerceve
        )

        buton_cercevesi.pack(
            fill=tk.X,
            pady=10,
            padx=5
        )

        ttk.Button(
            buton_cercevesi,
            text="1. JSON Dosyası Seç",
            command=self.dosya_yukle
        ).pack(
            side=tk.LEFT,
            padx=5
        )

        ttk.Button(
            buton_cercevesi,
            text="2. Sistemi Sıfırla (DROP)",
            command=self.veritabanini_sifirla
        ).pack(
            side=tk.LEFT,
            padx=5
        )

        ttk.Button(
            buton_cercevesi,
            text="3. SQL'e Dönüştür",
            command=self.donusumu_baslat
        ).pack(
            side=tk.LEFT,
            padx=5
        )
        # JSON Tree
        json_agac_cercevesi = ttk.Frame(
            sol_cerceve
        )

        json_agac_cercevesi.pack(
            fill=tk.BOTH,
            expand=True,
            padx=5,
            pady=5
        )

        self.json_agaci = ttk.Treeview(
            json_agac_cercevesi
        )

        self.json_agaci.heading(
            "#0",
            text="JSON Hiyerarşisi",
            anchor="w"
        )

        json_scroll_y = ttk.Scrollbar(
            json_agac_cercevesi,
            orient=tk.VERTICAL,
            command=self.json_agaci.yview
        )

        json_scroll_x = ttk.Scrollbar(
            json_agac_cercevesi,
            orient=tk.HORIZONTAL,
            command=self.json_agaci.xview
        )

        self.json_agaci.configure(
            yscrollcommand=(
                json_scroll_y.set
            ),
            xscrollcommand=(
                json_scroll_x.set
            )
        )

        self.json_agaci.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        json_scroll_y.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        json_scroll_x.grid(
            row=1,
            column=0,
            sticky="ew"
        )

        json_agac_cercevesi.rowconfigure(
            0,
            weight=1
        )

        json_agac_cercevesi.columnconfigure(
            0,
            weight=1
        )
        # RIGHT PANEL
        sag_cerceve = ttk.LabelFrame(
            ana_panel,
            text=(
                "SQL Sorgu Terminali "
                "ve DataGrid"
            )
        )

        ana_panel.add(
            sag_cerceve,
            weight=1
        )

        # Table selector
        tablo_cercevesi = ttk.Frame(
            sag_cerceve
        )

        tablo_cercevesi.pack(
            fill=tk.X,
            padx=5,
            pady=5
        )

        ttk.Label(
            tablo_cercevesi,
            text="Mevcut Tablolar:",
            font=(
                "Segoe UI",
                10,
                "bold"
            )
        ).pack(
            side=tk.LEFT
        )

        self.tablo_secici = ttk.Combobox(
            tablo_cercevesi,
            state="readonly",
            font=(
                "Segoe UI",
                10
            )
        )

        self.tablo_secici.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=5
        )

        self.tablo_secici.bind(
            "<<ComboboxSelected>>",
            self.tablo_secildiginde
        )

        ttk.Button(
            tablo_cercevesi,
            text="Tabloları Yenile",
            command=self.tablolari_yenile
        ).pack(
            side=tk.LEFT
        )

        #SQL terminal
        self.sql_metni = tk.Text(
            sag_cerceve,
            height=5,
            font=(
                "Consolas",
                11
            ),
            bg="#F4F4F4"
        )

        self.sql_metni.pack(
            fill=tk.X,
            padx=5,
            pady=5
        )

        self.sql_metni.insert(
            tk.END,
            "-- İşlem sonrası oluşan tabloları "
            "yukarıdan seçebilir\n"
            "-- veya buraya manuel sorgu "
            "yazabilirsiniz.\n"
        )

        ttk.Button(
            sag_cerceve,
            text="Sorguyu Çalıştır (Execute) ▶",
            command=self.sorguyu_calistir
        ).pack(
            pady=5,
            anchor="e",
            padx=5
        )
        # DATAGRID
        grid_cercevesi = ttk.Frame(
            sag_cerceve
        )

        grid_cercevesi.pack(
            fill=tk.BOTH,
            expand=True,
            padx=5,
            pady=5
        )

        self.sonuc_agaci = ttk.Treeview(
            grid_cercevesi,
            show="headings"
        )

        sonuc_scroll_y = ttk.Scrollbar(
            grid_cercevesi,
            orient=tk.VERTICAL,
            command=self.sonuc_agaci.yview
        )

        sonuc_scroll_x = ttk.Scrollbar(
            grid_cercevesi,
            orient=tk.HORIZONTAL,
            command=self.sonuc_agaci.xview
        )

        self.sonuc_agaci.configure(
            yscrollcommand=(
                sonuc_scroll_y.set
            ),
            xscrollcommand=(
                sonuc_scroll_x.set
            )
        )

        self.sonuc_agaci.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        sonuc_scroll_y.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        sonuc_scroll_x.grid(
            row=1,
            column=0,
            sticky="ew"
        )

        grid_cercevesi.rowconfigure(
            0,
            weight=1
        )

        grid_cercevesi.columnconfigure(
            0,
            weight=1
        )
        # LOG PANEL
        log_cercevesi = ttk.LabelFrame(
            self.ana_pencere,
            text=(
                "Sistem Logları ve "
                "Otonom SQL Çıktıları"
            )
        )

        log_cercevesi.pack(
            fill=tk.X,
            padx=10,
            pady=(
                0,
                10
            )
        )

        log_ic = ttk.Frame(
            log_cercevesi
        )

        log_ic.pack(
            fill=tk.X,
            padx=5,
            pady=5
        )

        self.log_konsolu = tk.Text(
            log_ic,
            height=14,
            bg="#1E1E1E",
            fg="#00FF00",
            font=(
                "Consolas",
                11,
                "bold"
            )
        )

        log_scroll_y = ttk.Scrollbar(
            log_ic,
            orient=tk.VERTICAL,
            command=self.log_konsolu.yview
        )

        self.log_konsolu.configure(
            yscrollcommand=(
                log_scroll_y.set
            )
        )

        self.log_konsolu.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True
        )

        log_scroll_y.pack(
            side=tk.RIGHT,
            fill=tk.Y
        )

        sys.stdout = CiktiYonlendirici(
            self.log_konsolu
        )

        self.tablolari_yenile()
    # JSON LOAD
    def dosya_yukle(self):

        dosya_yolu = (
            filedialog.askopenfilename(
                filetypes=[
                    (
                        "JSON Files",
                        "*.json"
                    )
                ]
            )
        )

        if not dosya_yolu:
            return

        try:

            with open(
                dosya_yolu,
                "r",
                encoding="utf-8"
            ) as dosya:

                self.yuklenen_json_verisi = (
                    json.load(
                        dosya
                    )
                )

            temel_ad = os.path.basename(
                dosya_yolu
            )

            ham_ad = os.path.splitext(
                temel_ad
            )[0]

            #Dosya adında boşluk/tire vb. olsa bile
            #güvenli root tablo adı oluşturulma
            self.guncel_tablo_adi = (
                self.motor.identifier_duzelt(
                    ham_ad
                )
            )

            self.json_agaci.delete(
                *self.json_agaci.get_children()
            )

            self.agaci_doldur(
                "",
                self.guncel_tablo_adi,
                self.yuklenen_json_verisi
            )

            print(
                f"[*] Bilgi: "
                f"'{temel_ad}' dosyası "
                f"sisteme yüklendi."
            )

            messagebox.showinfo(
                "Başarılı",
                f"'{temel_ad}' "
                "başarıyla yüklendi!"
            )

        except (
            OSError,
            json.JSONDecodeError
        ) as hata:

            self.yuklenen_json_verisi = None
            self.guncel_tablo_adi = ""

            messagebox.showerror(
                "JSON Hatası",
                f"Dosya okunamadı:\n{hata}"
            )
    # JSON TREE
    def agaci_doldur(
        self,
        ebeveyn,
        anahtar,
        deger
    ):

        dugum = self.json_agaci.insert(
            ebeveyn,
            "end",
            text=str(
                anahtar
            )
        )

        if isinstance(
            deger,
            dict
        ):

            for (
                alt_anahtar,
                alt_deger
            ) in deger.items():

                self.agaci_doldur(
                    dugum,
                    alt_anahtar,
                    alt_deger
                )

        elif isinstance(
            deger,
            list
        ):

            for (
                indeks,
                eleman
            ) in enumerate(
                deger
            ):

                self.agaci_doldur(
                    dugum,
                    f"[{indeks}]",
                    eleman
                )

        else:

            self.json_agaci.insert(
                dugum,
                "end",
                text=f": {deger}"
            )
    # DATABASE RESET
    def veritabanini_sifirla(self):

        onay = messagebox.askyesno(

            "Dikkat - Geri Alınamaz İşlem",

            "Bu işlem proje veritabanındaki "
            "PUBLIC şemasını ve içindeki tüm "
            "tabloları DROP CASCADE ile "
            "silecektir.\n\n"
            "Devam etmek istiyor musunuz?"
        )

        if not onay:
            return

        try:

            self.motor.reset_database()

            self._sonuc_gridini_temizle()

            self.tablolari_yenile()

            messagebox.showinfo(
                "Sistem Sıfırlandı",
                "Public schema ve içindeki "
                "tablolar başarıyla temizlendi."
            )

        except Exception as hata:

            messagebox.showerror(
                "Hata",
                f"Sıfırlama başarısız: "
                f"{hata}"
            )
    # MIGRATION
    def donusumu_baslat(self):

        if (
            self.yuklenen_json_verisi
            is None
        ):

            messagebox.showwarning(
                "Uyarı",
                "Lütfen önce bir JSON "
                "dosyası seçin!"
            )

            return

        try:

            #Önceki JSON analizinin bellekte kalmasını engeller
            #DB tablolarına dokunmaz.
            self.motor.clear_state()

            self.motor.process_data(
                self.guncel_tablo_adi,
                self.yuklenen_json_verisi
            )

            self.motor.execute_migration()

            self.tablolari_yenile()

            messagebox.showinfo(
                "Migrasyon Başarılı",
                "JSON verisi otonom olarak "
                "ilişkisel PostgreSQL tablolarına "
                "dönüştürüldü."
            )

        except Exception as hata:

            messagebox.showerror(
                "Migrasyon Hatası",
                str(
                    hata
                )
            )
    # TABLE LIST
    def tablolari_yenile(self):

        baglanti = None
        imlec = None

        try:

            baglanti = psycopg2.connect(
                **self.vt_ayarlari
            )

            imlec = baglanti.cursor()

            imlec.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )

            tablolar = [
                satir[0]
                for satir
                in imlec.fetchall()
            ]

            self.tablo_secici[
                "values"
            ] = tablolar

            if tablolar:

                self.tablo_secici.set(
                    "İncelemek için "
                    "bir tablo seçin..."
                )

            else:

                self.tablo_secici.set(
                    "Tablo bulunamadı..."
                )

        except Exception as hata:

            self.tablo_secici[
                "values"
            ] = []

            self.tablo_secici.set(
                "Tablo bulunamadı..."
            )

            print(
                "Tablolar çekilemedi: "
                f"{hata}"
            )

        finally:

            if imlec is not None:
                imlec.close()

            if baglanti is not None:
                baglanti.close()

    # AUTOMATIC SELECT
    def tablo_secildiginde(
        self,
        _olay=None
    ):

        secilen_tablo = (
            self.tablo_secici.get()
        )

        gecersiz_degerler = {

            "Tablo bulunamadı...",

            "İncelemek için "
            "bir tablo seçin..."
        }

        if (
            not secilen_tablo
            or secilen_tablo
            in gecersiz_degerler
        ):

            return

        baglanti = None

        try:

            baglanti = psycopg2.connect(
                **self.vt_ayarlari
            )

            #Tablo adı artık doğrudan f-string ile SQL'e eklenmiyor
            guvenli_sorgu = (

                sql.SQL(
                    "SELECT * FROM {};"
                ).format(

                    sql.Identifier(
                        secilen_tablo
                    )
                )
            )

            sorgu_metni = (
                guvenli_sorgu.as_string(
                    baglanti
                )
            )

            self.sql_metni.delete(
                "1.0",
                tk.END
            )

            self.sql_metni.insert(
                tk.END,
                sorgu_metni
            )

            self.sorguyu_calistir()

        except Exception as hata:

            self._sonuc_gridini_temizle()

            messagebox.showerror(
                "SQL Hatası",
                str(
                    hata
                )
            )

        finally:

            if baglanti is not None:
                baglanti.close()

    # GRID CLEAR
    def _sonuc_gridini_temizle(self):

        self.sonuc_agaci.delete(
            *self.sonuc_agaci.get_children()
        )

        self.sonuc_agaci[
            "columns"
        ] = ()

    # MANUAL SQL TERMINAl
    def sorguyu_calistir(self):

        sorgu = (
            self.sql_metni.get(
                "1.0",
                tk.END
            ).strip()
        )

        if not sorgu:
            return

        baglanti = None
        imlec = None

        try:

            baglanti = psycopg2.connect(
                **self.vt_ayarlari
            )

            imlec = baglanti.cursor()

            imlec.execute(
                sorgu
            )

            # cursor.description varsa sorgu result-set döndürmüştür.
            #
            # Bu sayede sadece SELECT değil:
            #
            # WITH ... SELECT
            # INSERT ... RETURNING
            #
            # gibi PostgreSQL sorguları da DataGrid'de gösterilebilir.
            if (
                imlec.description
                is not None
            ):

                satirlar = (
                    imlec.fetchall()
                )

                sutun_isimleri = [

                    aciklama[0]

                    for aciklama
                    in imlec.description
                ]

                self._sonuc_gridini_temizle()

                self.sonuc_agaci[
                    "columns"
                ] = sutun_isimleri

                for sutun in sutun_isimleri:

                    self.sonuc_agaci.heading(
                        sutun,
                        text=sutun
                    )

                    self.sonuc_agaci.column(
                        sutun,
                        width=max(
                            100,
                            min(
                                220,
                                len(
                                    str(
                                        sutun
                                    )
                                ) * 12
                            )
                        ),
                        anchor="center"
                    )

                for satir in satirlar:

                    self.sonuc_agaci.insert(
                        "",
                        tk.END,
                        values=satir
                    )

            else:

                baglanti.commit()

                self._sonuc_gridini_temizle()

                self.tablolari_yenile()

                messagebox.showinfo(
                    "Başarılı",
                    "Sorgu başarıyla çalıştırıldı "
                    "(sonuç kümesi döndürmedi)."
                )

            print(
                f"\n[SQL Yürütüldü] "
                f"{sorgu}"
            )

        except Exception as hata:

            if baglanti is not None:
                baglanti.rollback()

            # Hatalı sorgudan sonra eski başka tablonun satırlarını ekranda bırakma.
            self._sonuc_gridini_temizle()

            messagebox.showerror(
                "SQL Hatası",
                str(
                    hata
                )
            )

            print(
                f"\n[HATA] "
                f"{str(hata)}"
            )

        finally:

            if imlec is not None:
                imlec.close()

            if baglanti is not None:
                baglanti.close()


def main():

    kok_pencere = tk.Tk()

    ProlabArayuz(
        kok_pencere
    )

    kok_pencere.mainloop()


if __name__ == "__main__":
    main()