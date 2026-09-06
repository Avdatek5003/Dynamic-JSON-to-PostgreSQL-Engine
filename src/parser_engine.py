import hashlib
import re
import uuid

import psycopg2
from psycopg2 import sql


class PostgreSQLConverterEngine:

    POSTGRES_IDENTIFIER_LIMIT = 63

    def __init__(self, vt_ayarlari):
        self.vt_ayarlari = vt_ayarlari

        # JSON analizinden üretilecek tablo şemaları.
        self.veritabani_semasi = {}

        # Migration sırasında PostgreSQL'e aktarılacak kayıtlar.
        self.eklenecek_kayitlar = []
    #STATE MANAGEMENT
    def clear_state(self):
        """
        Bellekte tutulan analiz/migration durumunu temizler.
        Veritabanındaki tablolara dokunmaz.
        """
        self.veritabani_semasi = {}
        self.eklenecek_kayitlar = []
    # IDENTIFIER NORMALIZATION
    def identifier_duzelt(self, deger):
        """
        JSON key veya tablo isimlerini güvenli PostgreSQL
        identifier'larına dönüştürür.

        Örnek:
            "Customer Data"     -> customer_data
            "postal-code"       -> postal_code
            "order id"          -> order_id
            "123-value"         -> field_123_value

        PostgreSQL identifier limiti olan 63 karakter de korunur.
        """

        orijinal = str(deger).strip().lower()

        #Harf/rakam/underscore dışındaki karakterleri "_" yap.
        metin = re.sub(
            r"[^a-zA-Z0-9_]+",
            "_",
            orijinal
        )

        #Birden fazla "_" karakterini teke indir.
        metin = re.sub(
            r"_+",
            "_",
            metin
        )

        metin = metin.strip("_")

        #Tamamen özel karakterlerden oluşan bir key gelirse
        if not metin:
            metin = "field"

        #PostgreSQL identifier rakamla başlamasın
        if metin[0].isdigit():
            metin = f"field_{metin}"
       
        if len(metin) > self.POSTGRES_IDENTIFIER_LIMIT:

            digest = hashlib.sha1(
                metin.encode("utf-8")
            ).hexdigest()[:8]

            prefix_length = (
                self.POSTGRES_IDENTIFIER_LIMIT
                - len(digest)
                - 1
            )

            metin = (
                f"{metin[:prefix_length]}_{digest}"
            )

        return metin

 # TYPE INFERENCE

    def sql_tipi_belirle(self, deger):
        """
        Python veri tiplerini PostgreSQL veri tiplerine eşler.
        """

        if deger is None:
            return None

        #Python bool, int'in subclass'ıdır.
        #Bu nedenle bool kontrolü int'ten önce yapılmalıdır.
        if isinstance(deger, bool):
            return "BOOLEAN"

        if isinstance(deger, int):
            return "BIGINT"

        if isinstance(deger, float):
            return "NUMERIC"

        return "TEXT"

    def tipleri_birlestir(
        self,
        mevcut_tip,
        yeni_tip
    ):
        """
        Aynı sütunda farklı satırlarda farklı tipler bulunursa
        güvenli ortak PostgreSQL tipini belirler.

        Örnek:
            BIGINT + NUMERIC -> NUMERIC
            BIGINT + TEXT    -> TEXT
        """

        if mevcut_tip is None:
            return yeni_tip

        if yeni_tip is None:
            return mevcut_tip

        if mevcut_tip == yeni_tip:
            return mevcut_tip

        sayisal_tipler = {
            "BIGINT",
            "NUMERIC"
        }

        if {
            mevcut_tip,
            yeni_tip
        }.issubset(sayisal_tipler):

            return "NUMERIC"

        #Heterojen değerlerde veri kaybı yaşamamak için TEXT.
        return "TEXT"

    # JSON FLATTENING
    def sozlugu_duzlestir(
        self,
        sozluk,
        ust_anahtar="",
        ayrac="_"
    ):

        ogeler = []

        for anahtar, deger in sozluk.items():

            temiz_anahtar = self.identifier_duzelt(
                anahtar
            )

            yeni_anahtar = (
                f"{ust_anahtar}{ayrac}{temiz_anahtar}"
                if ust_anahtar
                else temiz_anahtar
            )

            yeni_anahtar = self.identifier_duzelt(
                yeni_anahtar
            )

            if isinstance(deger, dict):

                alt_ogeler = self.sozlugu_duzlestir(
                    deger,
                    yeni_anahtar,
                    ayrac=ayrac
                )

                ogeler.extend(
                    alt_ogeler.items()
                )

            else:

                ogeler.append(
                    (
                        yeni_anahtar,
                        deger
                    )
                )

        return dict(ogeler)
    # DATABASE RESET
    def reset_database(self):
        """
        Dedicated proje veritabanındaki public schema'yı tamamen
        sıfırlar.

       
        DROP SCHEMA public CASCADE çalıştırır
        GUI tarafında bu işlem öncesinde kullanıcı onayı alınır.
        """

        self.clear_state()

        with psycopg2.connect(
            **self.vt_ayarlari
        ) as baglanti:

            with baglanti.cursor() as imlec:

                print(
                    "\n[SİSTEM] Veritabanı sıfırlanıyor "
                    "(DROP SCHEMA public CASCADE)..."
                )

                imlec.execute(
                    """
                    DROP SCHEMA public CASCADE;
                    CREATE SCHEMA public;
                    """
                )

                print(
                    "[SİSTEM] Public schema yeniden oluşturuldu."
                )
    # JSON -> RELATIONAL MODEL
    def process_data(
        self,
        tablo_adi,
        veri_sozlugu,
        ust_id=None,
        yabanci_anahtar_adi=None,
        ust_tablo_adi=None
    ):
        """
        JSON yapısını recursively analiz eder.

        - Nested object -> flattened columns
        - Array/list -> child table
        - Her kayıt -> UUID tabanlı primary key
        - Parent-child ilişkisi -> foreign key metadata
        """

        tablo_adi = self.identifier_duzelt(
            tablo_adi
        )

        if yabanci_anahtar_adi is not None:

            yabanci_anahtar_adi = (
                self.identifier_duzelt(
                    yabanci_anahtar_adi
                )
            )

        if ust_tablo_adi is not None:

            ust_tablo_adi = self.identifier_duzelt(
                ust_tablo_adi
            )
        # LIST
        if isinstance(
            veri_sozlugu,
            list
        ):

            son_id = None

            for eleman in veri_sozlugu:

                #Primitive list elemanlarını da relational row yapma
                if not isinstance(
                    eleman,
                    dict
                ):

                    eleman = {
                        "deger": eleman
                    }

                son_id = self.process_data(
                    tablo_adi,
                    eleman,
                    ust_id=ust_id,
                    yabanci_anahtar_adi=(
                        yabanci_anahtar_adi
                    ),
                    ust_tablo_adi=(
                        ust_tablo_adi
                    )
                )

            return son_id

        #Primitive root veri gelirse dict'e sar.
        if not isinstance(
            veri_sozlugu,
            dict
        ):

            veri_sozlugu = {
                "deger": veri_sozlugu
            }
        # FLATTEN
        duz_veri = self.sozlugu_duzlestir(
            veri_sozlugu
        )

        guncel_id = str(
            uuid.uuid4()
        )
        # TABLE SCHEMA
        if (
            tablo_adi
            not in self.veritabani_semasi
        ):

            self.veritabani_semasi[
                tablo_adi
            ] = {

                "sutunlar": {
                    "id_pk": "VARCHAR(50)"
                },

                "yabanci_anahtarlar": []
            }

        satir_verisi = {
            "id_pk": guncel_id
        }
        # FOREIGN KEY METADATA
        if (
            ust_id is not None
            and yabanci_anahtar_adi is not None
            and ust_tablo_adi is not None
        ):

            self.veritabani_semasi[
                tablo_adi
            ]["sutunlar"][
                yabanci_anahtar_adi
            ] = "VARCHAR(50)"

            iliski = {

                "ust_tablo": (
                    ust_tablo_adi
                ),

                "ya_sutunu": (
                    yabanci_anahtar_adi
                )
            }

            if (
                iliski
                not in self.veritabani_semasi[
                    tablo_adi
                ]["yabanci_anahtarlar"]
            ):

                self.veritabani_semasi[
                    tablo_adi
                ]["yabanci_anahtarlar"].append(
                    iliski
                )

            satir_verisi[
                yabanci_anahtar_adi
            ] = ust_id
        #FIELDS
        for anahtar, deger in duz_veri.items():

            anahtar = self.identifier_duzelt(
                anahtar
            )
            #ARRAY ->CHILD TABLE
            if isinstance(
                deger,
                list
            ):

                alt_tablo_adi = (
                    self.identifier_duzelt(
                        f"{tablo_adi}_{anahtar}"
                    )
                )

                ya_sutun_adi = (
                    self.identifier_duzelt(
                        f"{tablo_adi}_id"
                    )
                )

                for eleman in deger:

                    if not isinstance(
                        eleman,
                        dict
                    ):

                        eleman = {
                            "deger": eleman
                        }

                    self.process_data(

                        alt_tablo_adi,

                        eleman,

                        ust_id=guncel_id,

                        yabanci_anahtar_adi=(
                            ya_sutun_adi
                        ),

                        ust_tablo_adi=(
                            tablo_adi
                        )
                    )
            #NORMAL FIELD
            else:

                yeni_tip = (
                    self.sql_tipi_belirle(
                        deger
                    )
                )

                mevcut_tip = (
                    self.veritabani_semasi[
                        tablo_adi
                    ]["sutunlar"].get(
                        anahtar
                    )
                )

                birlesik_tip = (
                    self.tipleri_birlestir(
                        mevcut_tip,
                        yeni_tip
                    )
                )

                self.veritabani_semasi[
                    tablo_adi
                ]["sutunlar"][
                    anahtar
                ] = birlesik_tip

                satir_verisi[
                    anahtar
                ] = deger

        #Row belleğe ekleme
        self.eklenecek_kayitlar.append(
            (
                tablo_adi,
                satir_verisi
            )
        )

        return guncel_id
    #VALUE NORMALIZATION BEFORE INSERT
    def _degeri_sql_icin_hazirla(
        self,
        tablo_adi,
        sutun_adi,
        deger
    ):

        if deger is None:
            return None

        hedef_tip = (
            self.veritabani_semasi[
                tablo_adi
            ]["sutunlar"].get(
                sutun_adi
            )
        )
        #Aynı kolonda heterojen tipler bulundu ve final tip TEXT olduysa, eski numeric/bool değerleri de text'e çevir.
        if (
            hedef_tip == "TEXT"
            and not isinstance(
                deger,
                str
            )
        ):

            return str(deger)

        return deger
    # MIGRATION
    def execute_migration(self):
  
        if not self.veritabani_semasi:

            raise ValueError(
                "Migration için şema bulunamadı. "
                "Önce process_data() çağrılmalıdır."
            )

        if not self.eklenecek_kayitlar:

            raise ValueError(
                "Migration için kayıt bulunamadı."
            )

        baglanti = psycopg2.connect(
            **self.vt_ayarlari
        )

        imlec = baglanti.cursor()

        try:
            # 1. CREATE TABLE
            print(
                "\n"
                + "=" * 60
            )

            print(
                "1. AŞAMA: "
                "DİNAMİK TABLOLARIN OLUŞTURULMASI"
            )

            for (
                tablo_adi,
                detaylar
            ) in self.veritabani_semasi.items():

                sutun_tanimlari = []

                for (
                    sutun_adi,
                    sutun_tipi
                ) in detaylar[
                    "sutunlar"
                ].items():

                    if (
                        sutun_adi
                        == "id_pk"
                    ):

                        sutun_tanimlari.append(

                            sql.SQL(
                                "{} VARCHAR(50) PRIMARY KEY"
                            ).format(

                                sql.Identifier(
                                    sutun_adi
                                )
                            )
                        )

                    else:

                        guvenli_tip = (
                            sutun_tipi
                            or "TEXT"
                        )

                        sutun_tanimlari.append(

                            sql.SQL(
                                "{} {}"
                            ).format(

                                sql.Identifier(
                                    sutun_adi
                                ),

                                # Tip değerleri yalnızca motorun kontrollü
                                # type inference fonksiyonundan gelir.
                                sql.SQL(
                                    guvenli_tip
                                )
                            )
                        )

                olusturma_sorgusu = (
                    sql.SQL(
                        "CREATE TABLE IF NOT EXISTS {} ({})"
                    ).format(

                        sql.Identifier(
                            tablo_adi
                        ),

                        sql.SQL(
                            ", "
                        ).join(
                            sutun_tanimlari
                        )
                    )
                )

                print(
                    "\n"
                    "[SİSTEM SQL YAZIYOR - CREATE]"
                )

                print(
                    olusturma_sorgusu.as_string(
                        baglanti
                    )
                )

                imlec.execute(
                    olusturma_sorgusu
                )
            # 2. INSERT
            print(
                "\n"
                + "=" * 60
            )

            print(
                "2. AŞAMA: "
                "VERİLERİN İLİŞKİSEL AKTARIMI"
            )

            # Recursive analiz sırasında child kayıtlar belleğe parent'tan önce eklenebilir.
            # FK constraintleri INSERT'lerden sonra eklense de,debug/log çıktısının daha doğal görünmesi için
            # kayıtları ters sırada geziyoruz.

            for (
                tablo_adi,
                satir_verisi
            ) in reversed(
                self.eklenecek_kayitlar
            ):

                sutunlar = list(
                    satir_verisi.keys()
                )

                degerler = [

                    self._degeri_sql_icin_hazirla(

                        tablo_adi,

                        sutun,

                        satir_verisi[
                            sutun
                        ]
                    )

                    for sutun in sutunlar
                ]

                ekleme_sorgusu = (

                    sql.SQL(
                        "INSERT INTO {} ({}) VALUES ({})"
                    ).format(

                        sql.Identifier(
                            tablo_adi
                        ),

                        sql.SQL(
                            ", "
                        ).join(
                            map(
                                sql.Identifier,
                                sutunlar
                            )
                        ),

                        sql.SQL(
                            ", "
                        ).join(

                            sql.Placeholder()
                            for _ in degerler
                        )
                    )
                )

                print(
                    "\n"
                    "[SİSTEM SQL YAZIYOR - INSERT]"
                )

                print(
                    ekleme_sorgusu.as_string(
                        baglanti
                    )
                )

                print(
                    f"  --> EKLENEN DEĞERLER: "
                    f"{degerler}"
                )

                imlec.execute(
                    ekleme_sorgusu,
                    degerler
                )
            # 3. FOREIGN KEYS
            print(
                "\n"
                + "=" * 60
            )

            print(
                "3. AŞAMA: "
                "FOREIGN KEY BAĞLANTILARI"
            )

            for (
                tablo_adi,
                detaylar
            ) in self.veritabani_semasi.items():

                for ya in detaylar[
                    "yabanci_anahtarlar"
                ]:

                    ust_tablo = (
                        ya[
                            "ust_tablo"
                        ]
                    )

                    ya_sutunu = (
                        ya[
                            "ya_sutunu"
                        ]
                    )

                    constraint_adi = (
                        self.identifier_duzelt(

                            f"fk_"
                            f"{tablo_adi}_"
                            f"{ya_sutunu}_"
                            f"{ust_tablo}"
                        )
                    )

                    #Aynı constraint bu tablo üzerinde zaten var mı kontrolü
                    imlec.execute(
                        """
                        SELECT 1
                        FROM pg_constraint c
                        JOIN pg_class t
                          ON t.oid = c.conrelid
                        JOIN pg_namespace n
                          ON n.oid = t.relnamespace
                        WHERE c.conname = %s
                          AND t.relname = %s
                          AND n.nspname = 'public'
                        """,
                        (
                            constraint_adi,
                            tablo_adi
                        )
                    )

                    if (
                        imlec.fetchone()
                        is not None
                    ):

                        continue

                    degistirme_sorgusu = (

                        sql.SQL(
                            """
                            ALTER TABLE {}
                            ADD CONSTRAINT {}
                            FOREIGN KEY ({})
                            REFERENCES {} ({})
                            ON DELETE CASCADE
                            """
                        ).format(

                            sql.Identifier(
                                tablo_adi
                            ),
                            sql.Identifier(
                                constraint_adi
                            ),
                            sql.Identifier(
                                ya_sutunu
                            ),

                            sql.Identifier(
                                ust_tablo
                            ),

                            sql.Identifier(
                                "id_pk"
                            )
                        )
                    )

                    print(
                        "\n"
                        "[SİSTEM SQL YAZIYOR - ALTER]"
                    )

                    print(
                        degistirme_sorgusu.as_string(
                            baglanti
                        )
                    )

                    imlec.execute(
                        degistirme_sorgusu
                    )

            baglanti.commit()

            print(
                "\n"
                + "=" * 60
            )

            print(
                "[MİGRASYON BAŞARILI] "
                "JSON verisi PostgreSQL ilişkisel "
                "yapısına dönüştürüldü."
            )

        except Exception as hata:

            baglanti.rollback()

            raise RuntimeError(
                "Veritabanı aktarım hatası: "
                f"{hata}"
            ) from hata

        finally:

            imlec.close()
            baglanti.close()