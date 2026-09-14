import json
import random
import datetime
import os

def generate_massive_log(filename="data/massive_logs.json", target_size_mb=100):
    print(f"[SİSTEM] {target_size_mb} MB boyutunda sentetik log üretiliyor. Lütfen bekleyin...")
    
    services = ["cart-service", "api-gateway", "auth-service", "payment-service", "user-db"]
    nodes = ["node-1", "node-2", "gateway-1", "db-node-1"]
    
    # Çok nadir gerçekleşecek o meşhur kriz senaryosu (İğne)
    kriz_senaryosu = [
        {"level": "WARNING", "message": "Memory usage at 85%."},
        {"level": "ERROR", "message": "DB_CONNECTION_TIMEOUT: Cannot connect to Redis cache."},
        {"level": "FATAL", "message": "OOMKilled. Node crashed."},
        {"level": "ERROR", "message": "HTTP 500 returned to 450 users."}
    ]
    
    start_time = datetime.datetime(2026, 9, 16, 12, 0, 0)
    
    # Belleği şişirmemek için dosyaya parça parça (streaming) yazıyoruz
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("[\n")
        
        current_size = 0
        target_bytes = target_size_mb * 1024 * 1024
        is_first = True
        
        while current_size < target_bytes:
            start_time += datetime.timedelta(seconds=random.randint(1, 5))
            
            # %99.9 INFO ve DEBUG gürültüsü üret
            log_entry = {
                "timestamp": start_time.isoformat(),
                "service": random.choice(services),
                "node": random.choice(nodes),
                "level": random.choice(["INFO", "DEBUG"]),
                "message": f"Normal system operation metric value: {random.randint(100, 999)}"
            }
            
            # Her 10.000 logda bir kriz senaryosunu (4 satır) araya sıkıştır
            if random.randint(1, 10000) == 1:
                for kriz in kriz_senaryosu:
                    start_time += datetime.timedelta(seconds=random.randint(1, 3))
                    kriz_log = {
                        "timestamp": start_time.isoformat(),
                        "service": "cart-service",
                        "node": "node-2",
                        "level": kriz["level"],
                        "message": kriz["message"]
                    }
                    if not is_first: f.write(",\n")
                    f.write(json.dumps(kriz_log))
            else:
                if not is_first: f.write(",\n")
                f.write(json.dumps(log_entry))
                is_first = False
            
            # Dosya boyutunu kontrol et
            current_size = f.tell()
            
        f.write("\n]")
    print(f"✅ Üretim tamamlandı! Dosya boyutu: {current_size / (1024*1024):.2f} MB")

# Hackathon testi için örneğin 50 MB (yüz binlerce satır) üretelim.
# Jüride bunu 1 GB yaparak "Büyük veri işleme" şovu yapabilirsiniz.
generate_massive_log(target_size_mb=50)