"""Synthetic training data generator with deterministic local offline generator for NDTM categories."""
from __future__ import annotations

import random
from typing import Any

TAXONOMY_CATEGORIES = [
    "POWER_GRID_FAILURE",
    "FIBER_CUT",
    "WATER_MAIN_BURST",
    "GAS_LEAK",
    "ROAD_COLLAPSE",
    "SIGNAL_INTERFERENCE",
    "TRANSFORMER_FIRE",
    "CYBER_TELEMETRY_ANOMALY",
]

# Domain-specific templates for realistic incident reports
_SAMPLE_TEMPLATES = {
    "POWER_GRID_FAILURE": [
        "Trafo merkezinde patlama meydana geldi, mahalle genelinde yüksek voltaj kesintisi yaşanıyor.",
        "Kuvvetli fırtına nedeniyle yüksek gerilim hattı koptu ve ana arter üzerine devrildi.",
        "Ana dağıtım panosunda aşırı yüklenme sonucu sigortalar attı, sanayi sitesinde elektrik yok.",
    ],
    "FIBER_CUT": [
        "Belediye altyapı kazısı sırasında ana fiber optik omurga kablosu iş makinesi tarafından koptu.",
        "Telekom menholünde meydana gelen fiziksel hasar nedeniyle bölgedeki tüm kurumsal internet hatları çöktü.",
        "Genişbant fiber santralinde optik sinyal kaybı tespit edildi, acil ekibin ek yapması gerekiyor.",
    ],
    "WATER_MAIN_BURST": [
        "İçme suyu ana isale hattında yüksek basınçtan dolayı boru patladı, caddeyi su bastı.",
        "Şebeke vanası kırıldı, su sızıntısı yakındaki konutların bodrum katlarına doğru yayılıyor.",
        "Kanalizasyon ve ana su borusu birleşme noktasında çökme ve yoğun taşkın var.",
    ],
    "GAS_LEAK": [
        "Doğalgaz dağıtım borusunda kazı kaynaklı delinme oldu, mahallede yoğun çürük sarımsak kokusu var.",
        "Regülatör istasyonunda basınç tahliye vanasından kontrolsüz gaz çıkışı gözleniyor.",
        "Bina girişindeki ana doğalgaz borusundan ıslık sesiyle gaz fışkırıyor, derhal tahliye gerekiyor.",
    ],
    "ROAD_COLLAPSE": [
        "Aşırı yağış sonrasında asfalt gövdesi çöktü, 3 metre derinliğinde obruk oluştu.",
        "Tünel girişinde zemin kayması ve şev çökmesi meydana geldi, çift yönlü trafik kapandı.",
        "Kaldırım ve yol birleşimindeki dolgu boşaldı, araçların geçişi imkansız hale geldi.",
    ],
    "SIGNAL_INTERFERENCE": [
        "Havalimanı yaklaşma koridorunda izinsiz yüksek güçlü telsiz yayını ve parazit tespit edildi.",
        "Halk güvenliği acil haberleşme frekansında sürekli RF bastırma ve parazit sinyali var.",
        "GSM baz istasyonu kule antenlerinde yönlü sinyal girişiminden ötürü bağlantı kopuyor.",
    ],
    "TRANSFORMER_FIRE": [
        "Cadde üzerindeki trafo patladı ve izolasyon yağı alev alarak bina cephesine sıçradı.",
        "Şalt sahasındaki güç trafosunda elektrik arkı sonrası kontrolsüz yangın başladı.",
        "Yer altı trafo köşkünden yoğun siyah duman ve patlama sesleri geliyor.",
    ],
    "CYBER_TELEMETRY_ANOMALY": [
        "SCADA telemetri sunucusuna yönelik anormal paket trafiği ve yetkisiz PLC komutları yakalandı.",
        "Akıllı şebeke sayaç verilerinde tutarsızlık ve TLS tünelinde MITM teşebbüsü tespit edildi.",
        "Kentsel IoT sensör ağı baz istasyonuna sahte telemetri paketleri enjekte ediliyor.",
    ],
}


class SyntheticIncidentGenerator:
    """Generates synthetic incident reports for offline distillation and testing."""

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    def generate_batch(self, count_per_category: int = 10) -> list[dict[str, Any]]:
        """Generates labeled dataset across all 8 taxonomy categories with varied urgency."""
        dataset: list[dict[str, Any]] = []

        for category in TAXONOMY_CATEGORIES:
            templates = _SAMPLE_TEMPLATES[category]
            for _ in range(count_per_category):
                base_text = self.rng.choice(templates)
                urgency = self.rng.randint(3, 10) if category in ("GAS_LEAK", "TRANSFORMER_FIRE", "POWER_GRID_FAILURE") else self.rng.randint(1, 8)

                # Add natural noise variations
                variation_suffix = f" Olay yerinde ekiplerin acil müdahalesi talep ediliyor. (Kod: #{self.rng.randint(100, 999)})"
                full_text = base_text + variation_suffix

                dataset.append(
                    {
                        "text": full_text,
                        "category": category,
                        "urgency_score": urgency,
                    }
                )

        self.rng.shuffle(dataset)
        return dataset
