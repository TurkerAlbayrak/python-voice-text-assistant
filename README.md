# Kişisel Haber ve Bilgi Asistanı

Python ile çalışan, **yapay zekâ / LLM kullanmayan**, sesli ve yazılı komut destekli kişisel haber ve bilgi asistanı.

## Özellikler

- **Haberler:** TRT, Anadolu Ajansı, Reuters, BBC RSS kaynakları (Türkiye, dünya, ekonomi)
- **Finans:** Dolar, Euro, Sterlin, gram altın, ons altın (TCMB + yedek kaynak)
- **Hava durumu:** OpenWeatherMap API
- **Sesli okuma:** Edge neural Türkçe ses (varsayılan), yedek pyttsx3
- **Sesli komut:** SpeechRecognition + Google Speech API (internet gerekir, LLM değildir)
- **Sabah brifingi:** Açılışta özet rapor (ekran + ses)

## Gereksinimler

- Python **3.11+**
- İnternet bağlantısı
- Mikrofon (sesli komut için)
- OpenWeatherMap API anahtarı ([ücretsiz kayıt](https://openweathermap.org/api))

## Kurulum

### 1. Projeyi indirin veya klonlayın

```bash
cd assistant
```

### 2. Sanal ortam oluşturun (önerilir)

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Bağımlılıkları yükleyin

```bash
pip install -r requirements.txt
```

Sesli okuma için **edge-tts** ve **pygame** zorunludur (MP3 çalma):

```bash
pip install edge-tts pygame
```

#### PyAudio (Windows)

`PyAudio` kurulumu Windows’ta hata verebilir. Alternatifler:

```powershell
pip install pipwin
pipwin install pyaudio
```

veya resmi wheel:

```powershell
pip install PyAudio
```

### 4. Yapılandırma

`config.json` dosyasını düzenleyin:

```json
{
  "openweather_api_key": "SIZIN_API_ANAHTARINIZ",
  "default_city": "Muğla",
  "voice": {
    "rate": 165,
    "volume": 1.0
  }
}
```

OpenWeatherMap anahtarını [buradan](https://home.openweathermap.org/api_keys) alabilirsiniz.

## Çalıştırma

```bash
cd assistant
python main.py
```

Varsayılan olarak **grafik arayüz** açılır. Konsol modu için:

```bash
python main.py --cli
```

### Arayüz özellikleri

- Sabah brifingi, hava, finans ve haber butonları
- Komut satırı ve hızlı kısayollar (Dolar, Euro, Altın)
- Otomatik sesli okuma aç/kapa
- Sesli komut (mikrofon) desteği
- Dünya haberleri **Türkçe kaynaklardan** (CNN Türk, NTV, TRT)

### Komut satırı seçenekleri

| Seçenek | Açıklama |
|---------|----------|
| `--no-briefing` | Sabah brifingini atla |
| `--silent` | Sesli okumayı kapat |
| `-c "dolar kaç"` | Tek komut çalıştır ve çık |

### Örnek yazılı komutlar

```
> dolar kaç
> euro kaç
> altın ne durumda
> hava durumu muğla
> ekonomi haberleri
> haberleri oku
> sesli mod
> çıkış
```

### Örnek sesli komutlar

Mikrofon modunda söyleyebilirsiniz:

- Haberleri oku
- Ekonomi haberlerini oku
- Dolar kaç
- Euro kaç
- Altın ne kadar
- Hava durumu
- Çıkış

## Klasör yapısı

```
assistant/
├── main.py
├── config.json
├── news.py
├── weather.py
├── finance.py
├── voice.py
├── commands.py
├── utils.py
├── requirements.txt
└── data/
```

## Gelecek özellikler

`utils.py` içindeki `FeatureRegistry` altyapısı şu modüller için hazırdır:

- Kripto para
- Borsa İstanbul
- Takvim
- Yapılacaklar listesi
- E-posta okuma
- Discord entegrasyonu
- METAR / havacılık

Yeni modül eklemek için:

```python
from utils import register_future_feature

def kripto_handler(command: str) -> str:
    ...

register_future_feature("kripto", kripto_handler, aliases=["bitcoin"])
```

## Sorun giderme

| Sorun | Çözüm |
|-------|--------|
| Hava durumu hatası | `config.json` içinde geçerli OpenWeatherMap anahtarı |
| Mikrofon yok | PyAudio kurulumu, Windows ses izinleri |
| Ses çıkmıyor | Aktif venv içinde: `pip install edge-tts pygame` sonra `python main.py` |
| Türkçe ses robotik | `config.json` → `"engine": "edge"`; `pygame` kurulu olmalı |
| Türkçe ses yok (çevrimdışı) | Windows’a Türkçe TTS paketi veya `engine: edge` (internet gerekir) |
| RSS boş | Kaynak geçici kapalı olabilir; interneti kontrol edin |
| Konuşma tanıma | İnternet ve Google Speech erişimi gerekir |

## Lisans

Bu proje eğitim ve kişisel kullanım için örnek olarak sunulmuştur.
