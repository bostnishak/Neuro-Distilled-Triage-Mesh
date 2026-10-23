# Değişiklik Günlüğü (Changelog)

Bu belgede TriageMesh projesindeki sürüm değişiklikleri, hata düzeltmeleri ve iyileştirmeler listelenmektedir.

## [1.2.0] - 2026-10-15

### Eklendi
- **TCKN Doğrulama ve Maskeleme:** Modulo-10/11 algoritmasıyla gerçek kimlik numarası kontrolü eklendi. Geçerli numaralar HMAC-SHA256 ile takma ada (`[REDACTED_TCKN_...]`) dönüştürülüyor.
- **Z3 unstat_core Çözümleyici:** İmkansız atamalarda (`UNSAT`) hangi ekibin kuralı bozduğu doğrudan hata mesajında gösteriliyor.
- **Transactional Outbox Relay:** RabbitMQ çift-yazma riskini önlemek için outbox_events tablosu ve arka plan relay işçisi yazıldı.

### Düzeltildi
- PostgreSQL `ST_DWithin` sorgusunda metre cinsinden yarıçapın `geography` tipine dökülmemesi sebebiyle oluşan mesafe hesaplama hatası giderildi.
- OpenCV Laplacian varyansı 100 altında kalan aşırı karanlık ve bulanık fotoğraflar için HTTP 422 yerine açıklayıcı `REJECTED_QUALITY` durum kodu dönüldü.
- Base64 gizlenmiş prompt injection saldırılarının try/except bloğunda yutulması sorunu çözüldü.

---

## [1.1.0] - 2026-09-28

### Eklendi
- **INT8 Kuantize ONNX Öğrenci Modeli:** Basit ihbarlar için CPU üzerinde çalışan kompakt model entegre edildi.
- **Shannon Entropi Yönlendirici:** Entropi eşiği 0.28 olarak belirlendi; kararsız durumlarda otomatik olarak ana LLM'e devir yapılıyor.
- **Devre Kesici (Circuit Breaker):** Üst LLM sağlayıcısında 5 ardışık hata oluştuğunda sistem OPEN durumuna geçip trafiği ONNX modeline yönlendiriyor.

### İyileştirildi
- asyncpg bağlantı havuzunda pgvector codec kaydı optimize edildi, connection sızıntıları önlendi.
- Redis Lua kayan pencere algoritmasıyla rate limiter eklendi.

---

## [1.0.0] - 2026-08-12

### İlk Sürüm
- FastAPI tabanlı asenkron REST API iskeleti.
- PostgreSQL 16 + PostGIS + pgvector veritabanı şeması.
- RabbitMQ kuyruk mimarisi ve temel triage işçisi.
- React 18 operasyon arayüzü ilk prototipi.
