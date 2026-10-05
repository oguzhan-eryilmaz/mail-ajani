# Mail Ajanı

Üç Gmail kutusunu günde 4 kez (00, 06, 12, 18) kontrol eder, yeni mailleri Telegram'a düğmeli kart
olarak yollar. Düğmeler (🗑 Çöp · 📦 Arşiv · ⭐ Önemli · ✓ Kalsın) anında Gmail'e uygulanır.
Kararlarından öğrenir: aynı gönderene 10 kez aynı karar → kesin kural; bir türde son 30 tahminin
29'u tutarsa → o türde kendi karar verir. Her otomatik işlem özette "↩ Geri al" ile gelir.

Tasarım: `docs/specs/2026-09-19-mail-ajani-design.md`

## Komutlar
- `.venv/bin/python -m mail_ajani durum`: son tur, kurallar, yetkiler
- `.venv/bin/python -m mail_ajani tur --force`: şimdi bir tur çalıştır
- `.venv/bin/python -m mail_ajani hesap-ekle ad@alan.com`: hesap bağla ya da iznini yenile
- `.venv/bin/python -m mail_ajani bot-kur`: Telegram botunu bağla
- `.venv/bin/python -m mail_ajani kategori-kur`: kategori listesi yoksa varsayılan sekiz kategoriyi kur; mevcut listeyi koru
- `.venv/bin/python -m mail_ajani kategorile`: veritabanındaki kategorisiz eski maillere yalnız kategori etiketi uygula
- `scripts/kur.sh` / `scripts/kaldir.sh`: arka plan servislerini kur/kaldır

Telegram'da: `/kurallar` öğrendiklerini gösterir ve sildirir, `/durum` son turu gösterir.

Kategoriler `config.json` içindeki `kategoriler` listesiyle açılır; anahtar yoksa veya liste boşsa
önceki davranış sürer. Güvenlik, Fatura (makbuz ve vergi dahil) ve İşbirliği her gönderenden
otomatik önemli olur. Ayrıntılar ve hata davranışları: [kategori raporu](docs/ozellik-kategoriler.md).

## Nerede ne var
- Veri: `~/Library/Application Support/mail-ajani/` (veritabanı, ayar, Google izin dosyası)
- Anahtarlar: macOS Anahtar Zinciri, servis adı `mail-ajani`
- Kayıtlar: `~/Library/Logs/mail-ajani/`
