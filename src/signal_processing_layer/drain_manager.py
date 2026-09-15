import os
import re
import json
import logging
import xxhash
import math
from collections import Counter
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence
from drain3.masking import MaskingInstruction

logger = logging.getLogger(__name__)

class DrainManager:
    def __init__(self, state_file="drain3_state.bin", sim_th=0.50, depth=4):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 1. KNOWLEDGE BASE YÜKLEME
        self.kb_path = os.path.join(current_dir, "knowledge_base.json")
        self._load_knowledge_base()

        # 2. DRAIN CONFIG YAPILANDIRMASI
        absolute_state_path = os.path.join(current_dir, state_file)
        self.config = TemplateMinerConfig()
        self.config.profiling_enabled = False
        self.sim_th = float(max(0.10, min(0.95, sim_th)))
        self.depth = int(max(2, min(10, depth)))
        self.config.drain_sim_th = self.sim_th
        self.config.drain_depth = self.depth 
        
        # 3. GELİŞMİŞ MASKELEME KURALLARI (Enterprise Standart)
        self.config.masking_instructions = [
            # IP Adresleri
            MaskingInstruction(pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", mask_with="IP"),
            # UUID / GUID
            MaskingInstruction(pattern=r"\b[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", mask_with="UUID"),
            # Bağımsız Sayılar (Portlar, Process ID'ler, Hata Kodları)
            # Not: Kelime içindeki sayıları (v1, x64) bozmaz, saf sayıları (39412) maskeler.
            MaskingInstruction(pattern=r"(?<![a-zA-Z0-9])\b\d+\b(?![a-zA-Z0-9])", mask_with="NUM"),
            # Hexadecimal değerler (0x...)
            MaskingInstruction(pattern=r"\b0x[0-9a-fA-F]+\b", mask_with="HEX"),
            # Dosya Yolları (Linux & Windows benzeri)
            MaskingInstruction(pattern=r"(/[a-zA-Z0-9\._\-]+)+", mask_with="PATH")
        ]

        # 4. PERSISTENCE VE MINER BAŞLATMA
        persistence = FilePersistence(absolute_state_path)
        self.miner = TemplateMiner(persistence_handler=persistence, config=self.config)
        logger.info(f"Drain3 Miner initialized. Knowledge Base loaded from {self.kb_path} | sim_th={self.sim_th:.2f} | depth={self.depth}")

    def _load_knowledge_base(self):
        """Sistemin sözlüğünü yükler. Dosya yoksa güvenli varsayılanları kullanır."""
        try:
            if os.path.exists(self.kb_path):
                with open(self.kb_path, 'r') as f:
                    data = json.load(f)
                    self.protected_keywords = data.get("protected_keywords", [])
                    self.pre_masking_attrs = data.get("pre_masking_attributes", [])
            else:
                logger.warning("knowledge_base.json not found! Using hardcoded defaults.")
                self.protected_keywords = ["login", "failed", "password", "invalid", "user", "root"]
                self.pre_masking_attrs = ["user_id", "dest_ip", "port", "token"]
        except Exception as e:
            logger.error(f"Error loading Knowledge Base: {e}")
            self.protected_keywords = ["login", "failed", "password"]
            self.pre_masking_attrs = ["user_id"]

    def _calculate_entropy(self, text):
        """Shannon Entropy: Metnin yapısal karmaşıklığını ölçer."""
        if not text: return 0
        counts = Counter(text)
        probs = [n / len(text) for n in counts.values()]
        entropy = -sum(p * math.log2(p) for p in probs)
        return round(entropy, 2)

    def _calculate_confidence(self, cluster_size, template_str, clean_log):
        """Confidence Score: Şablonun güvenilirliğini hesaplar."""
        # Frekans puanı (Logaritmik artış: 1=0.5, 10=0.75, 100=1.0 gibi)
        size_score = min(1.0, 0.5 + (math.log10(cluster_size) / 4) if cluster_size > 0 else 0.5)
        
        # Karmaşıklık puanı: <*> oranı düşükse şablon daha kalitelidir
        wildcard_count = template_str.count('<*>') + template_str.count('<NUM>') + template_str.count('<IP>')
        words = template_str.split()
        quality_score = 1.0 - (wildcard_count / len(words)) if words else 1.0
        
        return round(size_score * quality_score, 2)

    def _pre_process(self, log_message, attributes=None):
        """Logu sterilize eder, Parser verileriyle maskeler ve anahtar kelimeleri korur."""
        if not log_message: return ""
        
        # 1. Temel temizlik (Gereksiz boşluklar ve tırnaklar)
        log = re.sub(r'\s+', ' ', log_message.strip())
        log = log.replace('"', '').replace("'", "")
        
        # 2. PRE-MASKING: Parser'dan gelen alanları şablon motorundan önce gizle
        if attributes:
            for attr in self.pre_masking_attrs:
                val = attributes.get(attr)
                if val is not None:
                    # Değeri kendi etiketimizle kapatıyoruz (<USER_ID>, <PORT> vb.)
                    log = log.replace(str(val), f"<{attr.upper()}>")

        # 3. PROTECTING: Kritik kelimeleri 'FIX_' ile işaretle (Drain dokunmasın)
        for word in self.protected_keywords:
            log = re.sub(rf'\b{word}\b', f"FIX_{word}", log, flags=re.IGNORECASE)
        
        return log

    def extract_pattern(self, log_message, attributes=None):
        """Şablon keşfi yapar ve gelişmiş metrikleri döner."""
        try:
            # A. Entropi (Kaos) Ölçümü
            entropy = self._calculate_entropy(log_message)
            
            # B. Ön İşleme ve Koruma
            clean_log = self._pre_process(log_message, attributes)
            
            # C. Drain Motoru İşlemi
            result = self.miner.add_log_message(clean_log)
            template_str = result.get("template_mined", "UNKNOWN_PATTERN")
            
            # D. Koruma Eklerini Kaldır (FIX_ -> "")
            template_str = re.sub(r'FIX_', '', template_str, flags=re.IGNORECASE)
            
            cluster_size = result.get("cluster_size", 1)
            
            # E. Güven Skoru (Confidence)
            confidence = self._calculate_confidence(cluster_size, template_str, clean_log)
            
            return {
                "template_id": self._generate_template_hash(template_str),
                "template": template_str,
                "cluster_size": cluster_size,
                "entropy": entropy,
                "confidence": confidence
            }
        except Exception as e:
            logger.error(f"Drain extraction error: {e}")
            return {
                "template_id": "E_ERROR",
                "template": log_message,
                "cluster_size": 1,
                "entropy": 0,
                "confidence": 0
            }

    def _generate_template_hash(self, template_str):
        """Şablon stringini 8 karakterlik eşsiz bir ID'ye dönüştürür."""
        hash_str = xxhash.xxh64(template_str.encode('utf-8')).hexdigest()[:8]
        return f"E_{hash_str}"