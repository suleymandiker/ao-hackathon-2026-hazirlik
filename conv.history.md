## 🕒 Tarih: 2026-09-08 13:50:34

### 👤 Gönderilen Log Verisi:
```json
[
  {
    "timestamp": "2026-09-16T15:01:00",
    "service": "cart-service",
    "node": "node-1",
    "level": "INFO",
    "message": "User added item to cart."
  },
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 🤖 SAKA (Qwen35-122b) Yanıtı:


**Kök Neden:**
`cart-service` servisinin `node-2` üzerinde bellek sınırlarını aşması (OOM) sonucu çökmesi, zincirleme reaksiyonla API Gateway üzerinden 500 hatalarına yol açmıştır.

**Çözüm Önerisi:**
*   Hemen çökmüş `node-2` üzerindeki servisi yeniden başlatın veya otomatik ölçeklendirme (auto-scaling) ile yedek bir düğüm ekleyin.
*   `cart-service` uygulamasında bellek sızıntısı (memory leak) olup olmadığını belirlemek için derinlemesine profil analizi yapın.
*   Kubernetes veya konteyner yöneticisinde bellek limitlerini (limits) ve taleplerini (requests), mevcut kullanım oranına göre artırın.
*   Bellek kullanımının %80 seviyesinde uyarı verecek şekilde izleme (monitoring) eşiklerini güncelleyerek OOM durumundan önce önlem alınmasını sağlayın.
*   Redis bağlantı zaman aşımı hatasının (DB_CONNECTION_TIMEOUT) bellek baskısından mı yoksa ağ/Redis tarafındaki bir sorundan mı kaynaklandığını doğrulayın.

---

## 🕒 Tarih: 2026-09-14 10:37:21 | Model: Qwen35 | Süre: 101.36 sn

### 👤 Gönderilen Log Verisi:
```json
[
  {
    "timestamp": "2026-09-16T15:01:00",
    "service": "cart-service",
    "node": "node-1",
    "level": "INFO",
    "message": "User added item to cart."
  },
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 🤖 Yanıt:


**Kök Neden:**
`cart-service`'in node-2 düğümünde bellek sınırlarının aşılması (OOMKilled) sonucu oluşan servis çökmesi, Redis bağlantı kopukluğuna ve kullanıcı tarafında HTTP 500 hatalarına neden olmuştur.

**Çözüm Önerileri:**
*   Etkilenen düğümü (node-2) acilen yeniden başlatın veya otomatik ölçeklendirme (autoscaling) politikaları ile yeni pod örnekleri ekleyin.
*   Bellek kullanımını tetikleyen kod parçasını veya bellek sızıntısını (memory leak) tespit etmek için uygulama loglarını ve metriklerini derinlemesine inceleyin.
*   Container bellek limitlerini (memory limits) ve taleplerini (requests) gerçek kullanım verilerine göre yeniden yapılandırın ve artırın.
*   Bellek kullanımının kritik seviyelere (%80 ve üzeri) yaklaşması durumunda erken uyarı (alerting) mekanizmalarını güçlendirin.
*   Bağımlı servisler (Redis) ile bağlantı kopukluklarına karşı devre kesici (circuit breaker) ve yeniden deneme (retry) stratejilerini gözden geçirin.

---

## 🕒 Tarih: 2026-09-14 10:42:30 | Model: Qwen35 | Süre: 45.58 sn

### 👤 Gönderilen Log Verisi:
```json
[
  {
    "timestamp": "2026-09-16T15:01:00",
    "service": "cart-service",
    "node": "node-1",
    "level": "INFO",
    "message": "User added item to cart."
  },
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 🤖 Yanıt:


**Kök Neden (Root Cause):**
`cart-service` node-2'de aşırı bellek tüketimi sonucu tetiklenen Out Of Memory (OOM) hatası, Redis bağlantı kopukluğuna ve servis çökmesine neden olmuştur.

**Çözüm Önerileri:**
*   `cart-service` için bellek limitlerini (memory limits) artırın ve mevcut bellek sızıntısını (memory leak) analiz edin.
*   Kubernetes/Orkestrasyon katmanında bellek kullanımına dayalı otomatik ölçeklendirme (HPA) yapılandırın.
*   Redis bağlantı hatalarında devre kesici (circuit breaker) mekanizması ekleyerek çöküşün yayılmasını önleyin.
*   Bellek kullanım uyarı eşiklerini %85 yerine %70 seviyesine düşürerek proaktif müdahale sağlayın.
*   Kullanıcı etkisini azaltmak için hata toleranslı (fallback) yapılar ekleyin.

---

## 🕒 Tarih: 2026-09-14 10:47:08 | Model: Qwen35 | Süre: 77.46 sn

### 👤 Gönderilen Log Verisi:
```json
[
  {
    "timestamp": "2026-09-16T15:01:00",
    "service": "cart-service",
    "node": "node-1",
    "level": "INFO",
    "message": "User added item to cart."
  },
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 🤖 Yanıt:


**Kök Neden (Root Cause):**
`cart-service` servisinin `node-2` üzerinde bellek yetersizliği (OOM) nedeniyle çökmesi, önceden yaşanan yüksek bellek kullanımı ve Redis bağlantı zaman aşımıyla tetiklenmiştir.

**Çözüm Önerileri:**
*   `cart-service` konteynerleri için bellek limitlerini (memory limits) artırın ve kaynak tahsisini gözden geçirin.
*   Redis bağlantı havuzu (connection pool) yapılandırmasını optimize edin ve bağlantı zaman aşımı sürelerini (timeout) yeniden ayarlayın.
*   Bellek kullanımı %80 seviyesindeyken tetiklenen otomatik ölçeklendirme (Horizontal Pod Autoscaler) kuralları ekleyin.
*   Redis servis kesintilerine karşı devre kesici (circuit breaker) mekanizması uygulayarak hataların zincirleme yayılmasını önleyin.
*   Bellek kullanımı ve OOM riski için daha erken uyarı (alerting) eşikleri belirleyin ve proaktif izleme sağlayın.

---

## 🕒 Tarih: 2026-09-14 10:52:06 | Model: Qwen35 | Süre: 97.02 sn

### 👤 Gönderilen Log Verisi:
```json
[
  {
    "timestamp": "2026-09-16T15:01:00",
    "service": "cart-service",
    "node": "node-1",
    "level": "INFO",
    "message": "User added item to cart."
  },
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 🤖 Yanıt:


**Kök Neden (Root Cause):**
`cart-service` servisinin node-2 düğümünde bellek tükenmesi (OOM) sonucu oluşan çökme, Redis bağlantı zaman aşımını tetikleyerek kullanıcı tarafında HTTP 500 hatalarına neden olmuştur.

**Çözüm Önerileri:**
*   `cart-service` için bellek kotasını (memory limit) artırın ve mevcut kullanım desenini analiz edin.
*   Bellek sızıntısı (memory leak) olup olmadığını tespit etmek için kod incelemesi ve profil analizi yapın.
*   Bellek kullanımının %70 seviyesinde uyarı verecek şekilde izleme (monitoring) ve alarm kurallarını güncelleyin.
*   Redis bağlantı hatalarına karşı devre kesici (circuit breaker) mekanizması ekleyerek çökme zincirini kırın.
*   Kubernetes veya altyapı seviyesinde otomatik ölçeklendirme (auto-scaling) ve kendini onarma (self-healing) politikalarını gözden geçirin.

---

## 🕒 Tarih: 2026-09-14 11:07:58 | Model: DEEEPSEEK-v4-FLASH | Süre: 17.54 sn

### 👤 Gönderilen Log Verisi:
```json
[
  {
    "timestamp": "2026-09-16T15:01:00",
    "service": "cart-service",
    "node": "node-1",
    "level": "INFO",
    "message": "User added item to cart."
  },
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 🤖 Yanıt:
**Kök Neden (Root Cause):** 
`cart-service` üzerindeki node-2'de yaşanan bellek sızıntısı veya yetersiz heap tahsisi nedeniyle bellek kullanımının %85'e ulaşması, Redis bağlantı zaman aşımına (timeout) yol açmış ve ardından işletim sistemi tarafından OOMKilled (Out of Memory) ile process'in öldürülmesi, api-gateway üzerinden 450 kullanıcıya HTTP 500 hatası dönülmesine neden olmuştur.

---

**Çözüm Önerileri:**

**1. Acil Müdahale (Incident Response):**
- **Servisi Yeniden Başlatın:** OOMKilled olan node-2'deki `cart-service` pod'unu veya process'ini hemen yeniden başlatarak hizmeti ayağa kaldırın.
- **Yükü Dağıtın (Scale Out):** Trafiği diğer sağlıklı node'lara (node-1 vb.) yönlendirin veya yatay ölçeklendirme (horizontal scaling) yaparak yeni node'lar ekleyin.
- **Son Deploy'u Geri Alın (Rollback):** Eğer bu sorun son bir deploy'dan sonra başladıysa, bir önceki stabil sürüme hızlıca geri dönün.

**2. Kısa Vadeli İyileştirmeler (Short-term Fixes):**
- **Bellek Limitlerini Artırın:** Container veya JVM/Node.js heap limitlerini (ör. `-Xmx` veya `--max-old-space-size`) artırarak geçici bir nefes alma alanı sağlayın.
- **Redis Bağlantı Yönetimi:** Redis istemcisine bağlantı havuzu (connection pool) ve yeniden deneme (retry) mekanizması ekleyin. Ayrıca, bağlantı zaman aşımı (timeout) sürelerini kısaltarak kaynak tüketimini azaltın.
- **Sağlık Kontrolü (Health Check) ve Otomatik Yeniden Başlatma:** Kubernetes veya benzeri bir orkestrasyon kullanıyorsanız, `livenessProbe` ekleyerek OOM durumunda pod'un otomatik olarak yeniden başlatılmasını sağlayın.

**3. Uzun Vadeli Çözümler (Long-term Fixes):**
- **Bellek Profilleme ve Sızıntı Tespiti:** Uygulama kodunda bellek sızıntısına neden olan nesneleri (cache'ler, statik değişkenler, açık kalan stream'ler) tespit etmek için düzenli olarak heap dump analizi ve profiler (ör. JProfiler, YourKit, async-profiler) kullanın.
- **Erken Uyarı Alarmları:** Bellek kullanımı için alarm eşiğini %85'ten %70'e düşürün ve CPU, GC (Garbage Collection) süreleri, Redis bağlantı havuzu doluluk oranı gibi metrikleri de izleyerek proaktif uyarılar oluşturun.
- **Devre Kesici (Circuit Breaker) Uygulayın:** Redis'e erişimde hata oranı arttığında, hızlıca devre kesici açarak (circuit breaker) isteklerin Redis'e gitmesini engelleyin ve varsayılan (fallback) bir yanıt döndürün. Bu, kaynakların tükenmesini ve OOM'u önler.
- **Otomatik Ölçeklendirme (Auto-scaling):** Bellek kullanımına dayalı otomatik ölçeklendirme politikaları (Horizontal Pod Autoscaler) tanımlayarak, yük artışlarında otomatik olarak yeni node'lar ekleyin.
- **Bağımlılık Dayanıklılığı:** Redis gibi kritik bağımlılıklar için yüksek kullanılabilirlik (HA) yapılandırması (ör. Redis Sentinel veya Cluster) kurun ve bağlantı kopmalarında uygulamanın zarif bir şekilde davranmasını (graceful degradation) sağlayın.

---

## 🕒 Tarih: 2026-09-14 11:08:52 | Model: DEEEPSEEK-v4-FLASH | Süre: 16.42 sn

### 👤 Gönderilen Log Verisi:
```json
[
  {
    "timestamp": "2026-09-16T15:01:00",
    "service": "cart-service",
    "node": "node-1",
    "level": "INFO",
    "message": "User added item to cart."
  },
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 🤖 Yanıt:
**Kök Nedeni (Root Cause):**  
`cart-service` üzerindeki `node-2`'nin bellek kullanımının %85'ten hızla tırmanarak OOM (Out of Memory) nedeniyle çökmesi, Redis bağlantı zaman aşımına ve ardından API Gateway üzerinden 450 kullanıcıya HTTP 500 hatası dönülmesine yol açtı.

**Çözüm Önerisi:**  

- **Acil Müdahale:**  
  - Çöken `node-2` pod'unu/konteynerini hemen yeniden başlatın ve trafiği sağlıklı düğümlere yönlendirin.  
  - Redis bağlantı havuzundaki (connection pool) tıkanmış oturumları temizleyin ve gateway'deki hatalı istekleri boşaltın.

- **Kısa Vadeli Düzeltmeler:**  
  - `cart-service` konteynerine ait bellek limitlerini (memory limits) ve isteklerini (requests) artırın.  
  - Uygulamanın heap/bellek ayarlarını (JVM, Node.js vb.) optimize edin ve GC (Garbage Collection) loglarını aktifleştirin.  
  - Redis için bağlantı zaman aşımı (timeout) ve yeniden deneme (retry) politikalarını kısaltarak hızlı başarısız olmayı (fail-fast) sağlayın.

- **Uzun Vadeli İyileştirmeler:**  
  - Bellek sızıntısını tespit etmek için heap dump analizi ve profil oluşturma (profiling) yapın; kaynak koddaki gereksiz nesne tutulumlarını düzeltin.  
  - Redis'i yüksek kullanılabilirlik (HA) için cluster moduna alın ve tek nokta arızasını (SPOF) ortadan kaldırın.  
  - Redis bağlantı havuzu boyutunu ve boşta kalma sürelerini (idle timeout) uygulama trafiğine göre yeniden yapılandırın.  
  - Redis erişilemez olduğunda devreye girecek yerel önbellek (local cache) veya kuyruk tabanlı bir degrade (graceful degradation) mekanizması ekleyin.

- **İzleme ve Alarm:**  
  - Bellek kullanımı için %70 uyarı, %85 kritik alarm eşikleri tanımlayın ve otomatik ölçeklendirme (HPA) için bellek tabanlı metrikler ekleyin.  
  - Redis bağlantı havuzu doluluk oranı, GC süreleri ve OOM olayları için ayrıntılı metrikler ve panolar oluşturun.  
  - Uygulama bağımlılıkları (Redis) için devre kesici (circuit breaker) deseni uygulayarak zincirleme hataları önleyin.

---

## 🕒 Tarih: 2026-09-14 11:23:50 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 3.64 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 11:25:07 | Görev: Ajan_2_RCA_AgirTop | Model: teknocan__qwen35-122b-a10b-awq-teknocan | Süre: 76.78 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):


### 1. Kök Neden Analizi (Root Cause Analysis)

Logları incelediğimizde olay zinciri şu şekildedir:

1.  **Tetikleyici (Trigger):** `cart-service` (node-2), Redis cache'e bağlanamıyor (`DB_CONNECTION_TIMEOUT`). Bu, Redis servisinin yavaşladığını, düştüğünü veya ağ sorunları olduğunu gösterir.
2.  **Büyüme (Escalation):** Bağlantı hatası sonrası uygulama muhtemelen bir "retry storm" (tekrar deneme fırtınası) yaşamış veya hata durumunu yönetemeyerek bellek sızıntısı (memory leak) yaratmıştır.
3.  **Kırılma (Failure):** 5 saniye içinde `cart-service` pod'u bellek limitini aşmış ve Kubernetes tarafından **OOMKilled** (Out Of Memory Killed) olarak sonlandırılmıştır. Logdaki "Node crashed" ifadesi, muhtemelen pod'un node üzerindeki kaynak tüketimi nedeniyle düştüğünü veya izleme aracının node'u da etkilenmiş olarak raporladığını gösterir, ancak teknik olarak konteyner seviyesinde bir OOM olayıdır.
4.  **Etki (Impact):** `cart-service` düştüğü için, `api-gateway` bu servise ulaşamamış ve 450 kullanıcıya **HTTP 500** hatası döndürmüştür.

**Kök Neden:** Redis bağlantı sorunları nedeniyle tetiklenen retry döngüsü veya bellek sızıntısı sonucu `cart-service` pod'unun bellek limitini aşması ve OOMKilled olması.

---

### 2. Çözüm ve Uygulanacak Komutlar

Aşağıdaki adımları sırasıyla uygulayarak servisi ayağa kaldıracağız ve kaynak limitlerini optimize edeceğiz.

#### Adım 1: Mevcut Durumu ve Olayları Kontrol Et
Pod'un neden düştüğünü ve Redis'in durumunu doğrulayalım.

```bash
# cart-service podlarının durumunu kontrol et
kubectl get pods -n production -l app=cart-service

# OOMKilled olan pod'un detaylarını ve eventlerini incele (Pod adını yukarıdan al)
kubectl describe pod cart-service-<pod-id> -n production

# Çökmüş pod'un son loglarını (OOM öncesini) incele
kubectl logs cart-service-<pod-id> -n production --previous
```

#### Adım 2: Redis Servisini Kontrol Et
Sorunun kaynağı Redis olabilir, Redis'in sağlıklı çalıştığından emin olalım.

```bash
# Redis podlarının durumu
kubectl get pods -n production -l app=redis

# Redis servisine erişilebilir mi test et (opsiyonel)
kubectl exec -it redis-<pod-id> -n production -- redis-cli ping
```

#### Adım 3: Kaynak Limitlerini Artır ve Servisi Yeniden Başlat
`cart-service`'in bellek limitleri, hata durumlarını yönetmek için yetersiz kalmış. Limitleri artırıp rollout restart yapalım.

```bash
# Deployment'ın mevcut kaynak limitlerini gör
kubectl get deployment cart-service -n production -o yaml | grep -A 5 resources

# Bellek limitini artır (Örn: 512Mi'den 1Gi'ye çıkarıyoruz)
kubectl set resources deployment cart-service -n production --limits=memory=1Gi --requests=memory=512Mi

# Değişikliklerin uygulanması için rollout restart yap
kubectl rollout restart deployment cart-service -n production

# Yeni podların hazırlandığını bekle
kubectl rollout status deployment cart-service -n production
```

#### Adım 4: Servis Sağlığını Doğrula
Gateway üzerinden isteklerin düzgün çalışıp çalışmadığını kontrol et.

```bash
# Podlar Ready mi?
kubectl get pods -n production -l app=cart-service

# Gateway loglarında 500 hatası azaldı mı?
kubectl logs -n production -l app=api-gateway --tail=50 | grep "500"
```

---

### 3. Uzun Vadeli Önleyici Tedbirler (Post-Mortem)

Bu sorunun tekrarını önlemek için aşağıdaki değişiklikleri planınıza eklemelisiniz:

1.  **Circuit Breaker:** `cart-service` içinde Redis bağlantı hatalarında "retry storm" oluşmasını engellemek için Circuit Breaker pattern uygulayın.
2.  **HPA (Horizontal Pod Autoscaler):** Bellek kullanımı arttığında pod sayısını otomatik artıracak HPA konfigürasyonu ekleyin.
3.  **Redis HA:** Redis'in tek bir noktada (Single Point of Failure) olmaması için Sentinel veya Cluster moduna geçiş yapın.
4.  **Alerting:** `OOMKilled` ve `Connection Timeout` olayları için anlık uyarı (alert) kurun, kullanıcı hatası (500) görmeden önce müdahale edin.

---

## 🕒 Tarih: 2026-09-14 13:30:01 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 3.49 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 13:30:33 | Görev: Ajan_2_RCA_AgirTop | Model: teknocan__qwen35-122b-a10b-awq-teknocan | Süre: 31.13 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):


### 1. 🎯 Kök Neden (Root Cause)
`cart-service` uygulaması, Redis cache servisine bağlanamama (timeout) hatası nedeniyle aşırı hata döngüsü veya bağlantı havuzu şişmesi yaşamış, bu durum bellek tüketimini kritik seviyeye taşımıştır. Sonuç olarak, Kubernetes düğümü (`node-2`) üzerindeki konteyner bellek limitini aşarak OOMKilled (Out Of Memory Killed) durumuna düşmüş ve çökmüştür. Bu servis kaybı, `api-gateway` üzerinden gelen kullanıcı isteklerinin işlenememesine ve HTTP 500 hatalarına neden olmuştur.

### 2. 🧠 XAI - Karar Gerekçesi (Reasoning)
1.  **Zaman Çizelgesi Analizi:** Olaylar keskin bir sıralama izliyor. Önce (15:03:00) Redis bağlantı hatası, ardından 5 saniye sonra (15:03:05) bellek hatası (OOM), en son 5 saniye sonra (15:03:10) kullanıcıya yansıyan Gateway hatası görüldü.
2.  **Nedensellik Zinciri:** Redis bağlantı sorunu (`DB_CONNECTION_TIMEOUT`), `cart-service` içindeki retry mekanizmalarını tetikledi veya bağlantıların temizlenmesini engelledi. Bu durum bellek sızıntısına veya ani tüketimine yol açtı.
3.  **Kritik Hata:** `OOMKilled` mesajı, servisin kaynak yetersizliği nedeniyle zorla sonlandırıldığını doğrular.
4.  **Etki Alanı:** `cart-service` çökünce, bağımlı olan `api-gateway` (gateway-1) bu servise erişemediği için kullanıcıya 500 hatası döndürdü.

### 3. 🧾 Kanıtlar (Evidence)
Kararımı destekleyen log satırları şunlardır:
*   **Tetikleyici:** `{"timestamp": "2026-09-16T15:03:00", "service": "cart-service", "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."}`
*   **Çöküş:** `{"timestamp": "2026-09-16T15:03:05", "service": "cart-service", "level": "FATAL", "message": "OOMKilled. Node crashed."}`
*   **Kullanıcı Etkisi:** `{"timestamp": "2026-09-16T15:03:10", "service": "api-gateway", "message": "HTTP 500 returned to 450 users."}`

### 4. 🛠️ Çözüm ve Aksiyon (Actionable Scripts)
Aşağıdaki komutlar ile servisi yeniden başlatın, kaynak limitlerini kontrol edin ve Redis bağlantısını doğrulayın.

```bash
# 1. Etkilenen pod'un durumunu kontrol et
kubectl get pods -n production -l app=cart-service -o wide

# 2. OOMKilled hatası veren pod'u yeniden başlat (Rolling restart)
kubectl rollout restart deployment/cart-service -n production

# 3. Pod'un yeniden başlamasından sonra logları kontrol et
kubectl logs -f deployment/cart-service -n production --tail=50

# 4. Redis servisinin erişilebilirliğini doğrula (Service discovery)
kubectl exec -it deployment/api-gateway -n production -- curl -v http://redis-service:6379

# 5. Bellek limitlerini ve kullanımını gözden geçir (Gelecek OOM'u önlemek için)
kubectl describe pod -l app=cart-service -n production | grep -A 5 "Limits"
```

---

## 🕒 Tarih: 2026-09-14 14:48:02 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 5.56 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 15:05:10 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 3.20 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 15:07:11 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 3.44 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 15:12:23 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 4.28 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 16:02:05 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 3.27 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 16:23:07 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 3.53 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 16:49:58 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 3.35 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 17:56:32 | Görev: Ajan_1_Triyaj | Model: deepseek-v4-flash-0731 | Süre: 8.40 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:02:15",
    "service": "cart-service",
    "node": "node-2",
    "level": "WARNING",
    "message": "Memory usage at 85%."
  },
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]

---

## 🕒 Tarih: 2026-09-14 17:58:19 | Görev: Ajan_2_RCA_AgirTop | Model: teknocan__qwen35-122b-a10b-awq-teknocan | Süre: 107.67 sn

### 📥 Girdi (Input):
```text
[
  {
    "timestamp": "2026-09-16T15:03:00",
    "service": "cart-service",
    "node": "node-2",
    "level": "ERROR",
    "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
  },
  {
    "timestamp": "2026-09-16T15:03:05",
    "service": "cart-service",
    "node": "node-2",
    "level": "FATAL",
    "message": "OOMKilled. Node crashed."
  },
  {
    "timestamp": "2026-09-16T15:03:10",
    "service": "api-gateway",
    "node": "gateway-1",
    "level": "ERROR",
    "message": "HTTP 500 returned to 450 users."
  }
]
```

### 📤 Çıktı (Output):


### 1. 🎯 Kök Neden (Root Cause)
`cart-service` uygulamasının bellek kotasını aşması (OOMKilled) sonucu pod'unun çökmesi ve hizmetin tamamen kesintiye uğraması. Redis cache bağlantı zaman aşımı (Timeout), muhtemelen bağlantı havuzunda sızıntıya (connection leak) veya başarısız istekler üzerindeki aşırı yeniden deneme (retry storm) döngülerine neden olarak bellek tüketimini tetiklemiştir.

### 2. 🧠 XAI - Karar Gerekçesi (Reasoning)
1.  **Zaman Çizelgesi Analizi:** Olaylar 5 saniyelik aralıklarla gerçekleşmiştir. Önce Redis bağlantı hatası (15:03:00), ardından 5 saniye sonra OOMKilled (15:03:05) ve son olarak API Gateway'de kullanıcı etkisi (15:03:10) görülmüştür. Bu sıralama, Redis sorununun OOM'u tetiklediğini, OOM'un ise Gateway hatasına yol açtığını gösterir.
2.  **Hata Seviyesi Önceliği:** `ERROR` seviyesindeki Redis hatası bir uyarıdır, ancak `FATAL` seviyesindeki `OOMKilled` olayı servisin tamamen durmasına neden olan kritik olaydır.
3.  **Bağımlılık Zinciri:** `api-gateway`'in 500 hatası, `cart-service`'in erişilemez hale gelmesinin bir sonucudur (Cascade Failure). Dolayısıyla kök neden Gateway değil, alt katmandaki `cart-service` çökmesidir.
4.  **Teknik Mantık:** Uygulama dışarıdan (Redis) veri çekemeyince bekleyen istekleri bellekte tutmuş veya bağlantıyı kapatamamış olabilir, bu da bellek doluluğunu (Memory Pressure) ve sonuçta OOMKilled durumunu yaratmıştır.

### 3. 🧾 Kanıtlar (Evidence)
Karar verirken aşağıdaki log satırlarına dayanılmıştır:

*   **Tetikleyici Olay:**
    ```json
    {
      "timestamp": "2026-09-16T15:03:00",
      "service": "cart-service",
      "node": "node-2",
      "level": "ERROR",
      "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."
    }
    ```
*   **Kritik Çökme Olayı (Kök Neden):**
    ```json
    {
      "timestamp": "2026-09-16T15:03:05",
      "service": "cart-service",
      "node": "node-2",
      "level": "FATAL",
      "message": "OOMKilled. Node crashed."
    }
    ```
*   **Kullanıcı Etkisi (Sonuç):**
    ```json
    {
      "timestamp": "2026-09-16T15:03:10",
      "service": "api-gateway",
      "node": "gateway-1",
      "level": "ERROR",
      "message": "HTTP 500 returned to 450 users."
    }
    ```

### 4. 🛠️ Çözüm ve Aksiyon (Actionable Scripts)
Hemen uygulanması gereken acil durum ve inceleme komutları:

```bash
# 1. Cart-service podlarının mevcut durumunu kontrol et
kubectl get pods -l app=cart-service -n production

# 2. Çöken pod'un detaylarını ve OOM geçmişini incele
kubectl describe pod <cart-service-pod-name> -n production | grep -A 5 "Last State"

# 3. Deployment'ı yeniden başlatarak servisi ayağa kaldır
kubectl rollout restart deployment/cart-service -n production

# 4. Bellek limitlerini ve taleplerini geçici olarak artır (Acil durum)
kubectl edit deployment cart-service -n production
# resources.limits.memory değerini %50 artırın (Örn: 512Mi -> 768Mi)

# 5. Redis bağlantı durumunu ve gecikmesini kontrol et
kubectl exec -it <redis-pod-name> -n production -- redis-cli ping

# 6. Sonraki 10 dakika boyunca cart-service bellek metriklerini izle
kubectl top pods -l app=cart-service -n production --sort-by=mem
```

---

