# TriageMesh

Belediye ve altyapı arıza ihbarlarını (elektrik kesintisi, su borusu patlağı, doğalgaz kaçağı, yol çökmesi vb.) otomatik olarak sınıflandıran, mükerrer bildirimleri filtreleyen ve saha ekiplerine atayan bir arka plan servisidir.

Büyük dil modellerinin (LLM) yüksek API maliyetini ve atama yaparken yaşadığı kural ihlallerini (halüsinasyon) önlemek için; küçük bir yerel model (ONNX INT8) ve matematiksel kısıt çözücü (Z3 SMT Solver) ile hibrit olarak çalışır.

---

## Ne İşe Yarar? (Problem ve Çözüm)

Saha operasyonlarında karşılaşılan 3 ana probleme çözüm üretir:

1. **Mükerrer Bildirim Fırtınası:** Bir ana caddeye su bastığında onlarca kişi aynı olayı bildirir. Sistem, gelen ihbarın koordinatına (250m yarıçap) ve metin benzerliğine (pgvector kosinüs benzerliği > 0.86) bakar. 48 saat içinde açılmış benzer bir ihbar varsa yeni kayıt oluşturmaz; mevcut kaydın sayacını artırıp birleştirir.
2. **Yüksek LLM Maliyeti & Gecikme:** Her basit ihbarı ("kaldırımda çukur var") pahalı büyük modellere göndermek hem saniyeler sürer hem maliyetlidir. Sistem önce yerel 8-bit kuantize ONNX modelini dener. Model karardan eminse (~6ms) doğrudan yanıtlar. Sadece karmaşık, belirsiz veya tehlikeli durumlarda büyük modele (OpenAI / Claude) devreder.
3. **Halüsinasyon Riski (Yanlış Ekip Atama):** Bir dil modeline "bu gaz kaçağına kimi yollayalım?" diye sorulduğunda, vardiyası bitmiş veya doğalgaz sertifikası olmayan bir ekibi gayet ikna edici şekilde önerebilir. Bu projede LLM sadece öneri sunabilir; nihai atama Z3 Teorem Çözücü tarafından sertifika, kalan vardiya süresi ve mesafe kuralları kontrol edilerek matematiksel kesinlikle yapılır.

---

## Mimari Akış

```text
[Vatandaş / Saha Bildirimi]
           │
           ▼
[Nginx Ters Proxy :80]
           │
           ▼
[FastAPI Backend :8000]
     ├── 1. Güvenlik & Ön Filtre:
     │      - Redis kayan pencere rate limiter (IP başına 120 req/dk)
     │      - TCKN algoritma kontrolü (Modulo-10/11) ve HMAC-SHA256 maskeleme
     │      - Bulanık fotoğraf filtresi (OpenCV Laplacian varyansı < 100 ise baştan red)
     │      - OWASP prompt injection filtresi
     │
     ├── 2. Mükerrer Kontrolü (PostgreSQL 16):
     │      - PostGIS ST_DWithin (250 metre) + pgvector (384-D HNSW kosinüs benzerliği)
     │      - Mükerrerse -> Parent kayıt sayacını artır
     │      - Yeni ihbarsa -> Outbox tablosuna yaz (Transactional Outbox Pattern)
     │
     ├── 3. Asenkron Olay Kuyruğu (RabbitMQ 3.13):
     │      - Outbox relay servisi 250ms aralıkla mesajları RabbitMQ'ya iletir
     │      - Başarısız veya zehirli mesajlar q.dlq.failed kuyruğuna düşer
     │
     ├── 4. Hibrit Model Yönlendirici (Router):
     │      - Redis Semantik Önbellek (Benzerlik >= 0.96 ise <2ms)
     │      - ONNX INT8 Öğrenci Modeli (Düşük entropi H <= 0.28 ise CPU'da ~6ms)
     │      - Büyük Dil Modeli (Yüksek entropili / karmaşık durumlarda devreye girer)
     │      - Devre Kesici (Circuit Breaker): Üst servis çökerse otomatik öğrenci modele geçer
     │
     └── 5. Saha Ekibi Atama (Z3 SMT Solver):
            - Zorunlu sertifika ve yetkinlik kontrolü
            - Kalan vardiya süresi kontrolü (Haversine seyahat süresi + tahmini çalışma)
            - Eşzamanlı maksimum iş limiti
            - Uyuşmazlık varsa 'unsat_core' ile sebebi açıklar ve z3.Optimize ile en yakın çözümü üretir
```

---

## Hızlı Başlangıç

### Gereksinimler
- Docker Engine 24.0+ ve Docker Compose v2.20+
- 4 CPU çekirdeği, minimum 6-8 GB RAM

### 1. Servisleri Başlatma
```bash
# Proje dizinine geçin
cd ndtm-enterprise

# Örnek ortam değişkenlerini kopyalayın
cp .env.example .env

# Tüm servisleri derleyip arka planda başlatın
docker compose up -d --build
```

Ayağa kalkan servisler:
- **Web Operasyon Paneli:** `http://localhost:3000`
- **FastAPI Backend (Swagger API):** `http://localhost:8000/docs`
- **PostgreSQL (PostGIS + pgvector):** `localhost:5432`
- **RabbitMQ Yönetim Paneli:** `http://localhost:15672` (Kullanıcı: `ndtm_user`, Şifre: `ndtm_secret_amqp_pass_2026!`)
- **Prometheus Metrikleri:** `http://localhost:9090`

---

## Yerel Geliştirme (Local Dev)

Docker yerine yerel ortamda çalıştırmak isterseniz:

```bash
# 1. Sanal ortamı hazırlayın
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 2. Bağımlılıkları yükleyin
pip install -r backend/requirements.txt

# 3. Testleri çalıştırın
pytest backend/tests/ -v

# 4. Frontend geliştirme sunucusu
cd frontend
npm install
npm run dev
```

---

## Test Paketi

Projede hem birim mantık testleri hem de dayanıklılık (chaos) testleri yer alır:

```bash
# Birim testleri çalıştırma (27 test)
pytest backend/tests/ -v

# Kaos testlerini çalıştırma (Devre kesici, prompt injection, DLQ replay)
python load_tests/chaos_injector.py --url http://localhost:8000 --scenario all

# Yük testi (Locust ile eşzamanlı kullanıcı simülasyonu)
locust -f load_tests/locustfile.py --host http://localhost:8000
```

---

## Konfigürasyon (.env)

| Değişken | Varsayılan Değer | Açıklama |
|---|---|---|
| `POSTGRES_DB` | `ndtm_enterprise_db` | PostgreSQL veritabanı adı |
| `EMBEDDING_DIMENSION` | `384` | pgvector vektör boyutu (MiniLM uyumlu) |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.86` | Mükerrer ihbar kosinüs benzerlik eşiği |
| `DEDUP_SPATIAL_RADIUS_METERS` | `250.0` | Mükerrer ihbar coğrafi yarıçapı (metre) |
| `IMAGE_LAPLACIAN_VAR_THRESHOLD`| `100.0` | Minimum netlik varyansı (altındakiler reddedilir) |
| `STUDENT_ENTROPY_THRESHOLD` | `0.28` | INT8 model güven eşiği (Shannon entropisi) |
| `RATE_LIMIT_PER_MINUTE` | `120` | IP başına dakikalık maksimum istek |
| `CRITICAL_URGENCY_SLA_MINUTES` | `45` | Acil durumlarda maksimum varış süresi |

---

## Geliştirici Notları & Tasarım Kararları

1. **Neden ayrı vektör veritabanı (Pinecone/Qdrant) yerine PostgreSQL + pgvector?**
   İhbar verisi ilişkiseldir (durum, zaman, vatandaş bilgisi, ekip ilişkisi). Ayrı bir vektör veritabanı kullanmak çift yazma (dual-write) tutarsızlığına yol açıyordu. PostgreSQL 16 üzerinde `pgvector` ve `PostGIS` bir arada tutularak tek bir SQL sorgusunda hem mesafe (`ST_DWithin`) hem kosinüs benzerliği (`1 - (embedding <=> $1)`) atomik olarak kilitlenerek (`FOR UPDATE`) çözüldü.

2. **Neden Transactional Outbox Pattern?**
   İhbarı veritabanına kaydederken RabbitMQ'ya doğrudan mesaj göndermek, ağ kopmasında veri kaybına yol açabilir. Bu yüzden ihbar ve outbox olayı aynı DB transaction'ı içinde yazılır. Ayrı bir relay işçisi 250ms aralıkla bu tabloyu tarar ve RabbitMQ'ya 'publisher confirm' garantisiyle iletir.

3. **Neden Z3 Solver?**
   Saha atamaları tipik bir NP-hard problemdir. Açgözlü (greedy) algoritmalar veya LLM promptları sınır koşullarında (örneğin elektrik teknisyeninin vardiyasında sadece 30 dakika kalmışken 45 dakikalık işe atanması) saçmalar. Z3, First-Order Logic kurallarıyla matematiksel olarak kesin çözüm üretir ya da neden atanamadığını (`unsat_core`) döner.
