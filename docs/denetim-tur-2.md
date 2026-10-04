# Mail Ajanı: bağımsız denetim, tur 2 (düzeltme doğrulaması)

Tarih: 5 Ekim 2026 · Denetleyen: Opus (salt okunur) · Konu: commit edilmemiş düzeltmeler (`git diff`, yeni `tests/test_launchd.py`)
ve [düzeltme raporu](duzeltme-tur-1.md), [tur 1 denetimi](denetim-tur-1.md)'ne göre.

## Karar

**Hayır, bu hâliyle değil.** Gerekçe: aşağıdaki **Y1** (yeni engel) düzeltilmeli. Düzeltme tek satırlık. Y1 yalnız launchd ile çalışan
zamanlanmış turu etkiliyor. `scripts/kur.sh` çalıştırılmadan, elle `tur --force` ile tek hesaplı gözetimli deneme bugünkü kodla güvenli:
mail kaybı, çift Gmail işlemi ya da çift kart üreten bir yol bulmadım. Y1 düzelince kod gözetimli canlı kuruluma hazır.

Tur 1'deki 11 bulgunun 11'i gerçek kod yolunda kapandı. Yeni StartInterval/yarım dilim mantığı ise bir hesap bozuk olduğunda
15 dakikada bir uyarı yollayan, kartları da günde 4 kez yerine 15 dakikada bir dağıtan bir döngü getirdi.

## Çalıştırılan kontroller ve sonuçları

| Kontrol | Sonuç |
|---|---|
| `MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q` | geçti (154 passed) |
| Tur 1 yeniden üretimleri R1, R2, R3, R4, R5, R9 yeni kodla (sahte Telegram artık gerçek istemci gibi `TelegramError` fırlatıyor) | R1-R5 kapandı; R9 `run_tur` seviyesinde hâlâ çift (beklenen, kilit CLI'da), CLI kilidi ayrıca denendi |
| Gerçek `cmd_tur` kilidi: ayrı bir Python süreci `tur.lock`'u tutarken `python -m mail_ajani tur --force` | geçti ("Başka bir tur çalışıyor; bu tur atlandı.", çıkış 0); kilit bırakılınca bir sonraki çağrı kilidi aldı |
| Gerçek `TelegramClient._call` yeniden deneme davranışı (sahte HTTP oturumu, `sleep` kayıtlı) | geçti: 429 kısa → 1 tekrar; 429 600 sn → tekrar yok, `retry_after=600`; 5xx ve bağlantı hatası → 4 deneme, bekleme [1, 2, 4]; 400 ve 401 → tekrar yok; hiçbir hata metninde anahtar/URL yok |
| Ö3, gerçek `cmd_dinle` kapanışı üzerinden (yalnız ayar/sır/kurucu sahte) | geçti: yetki hatasında istemci düştü, ikinci basışta yeniden kuruldu ve işlem uygulandı; ayara yeni eklenen hesap kuruldu |
| Ö6 boş gönderen | geçti (`rule_for('') is None`, `auto_action('', 'cop', {'cop'}) is None`) |
| Yeni senaryolar N1-N5 (yarım dilim, 15 dk tekrar, kalıcı 400, uzun `retry_after`) | N1, N2, N3 sorun gösterdi; N4, N5 doğru |
| `plutil -lint launchd/*.plist` ve `kur.sh`'deki `sed` ile üretilmiş kopyalar + `plutil -p` | geçti |
| `bash -n scripts/kur.sh scripts/kaldir.sh` | geçti |
| `mail_ajani/` içinde `.delete(`, `batchDelete`, `UNREAD`, `threads(` | yok (geçti) |
| Test sayısının dökümü (`pytest --collect-only`, `git show HEAD:` ile karşılaştırma) ve silinen test satırlarının incelemesi | meşru (aşağıda) |
| Gerçek Gmail, Telegram, `claude`, launchd yükleme, Anahtar Zinciri | çalıştırılmadı (kapsam dışı) |

## Tur 1 bulgularının durumu

| Bulgu | Durum | Kanıt |
|---|---|---|
| E1 otomatik karar bildirilmeden kayboluyor | **kapandı** | R1 yeni kodla: Telegram düşükken otomatik ⭐ uygulandı; sonraki iki turda özet + kart + uyarı geldi, `sent_at` doldu, Gmail işlemi **bir kez**: `gmail applied: [('g901', 'onemli')]`. `pending_mails` artık yalnız kullanıcı kararlarını eliyor (`db.py:68-72`); bildirim `decisions.notified_at` ile (`tur.py:107-113`). Eski veritabanı sütun geçişi test edildi. |
| E2 beklenmeyen Claude çıktısı turu çökertiyor | **kapandı** | R2: `'[]' -> ({}, ['beklenmeyen dış çıktı biçimi'])`, `"metin"`, `items: null`, `["x"]` aynı şekilde; uçtan uca `telegram: 3 last_run: … pending: 0`. `classify` her istisnayı yakalıyor (`classifier.py:99-103`), `run_tur` da ayrıca sarıyor (`tur.py:48-51`). |
| E3 Telegram hatası turu kesiyor, 6 saat bekliyor | **kapandı (yan etkiyle, bkz. Y1)** | R5: 21. mesajda hata → `last_run` yazılmadı, sonraki çağrıda 20 kart + uyarı geldi, çift kart yok. Gerçek istemcide 429/5xx/bağlantı tekrarları sınırlı (yukarıdaki tablo). N5: `retry_after=600` → 12:05'te erken deneme yok, 12:15'te devam, 12:30'da atlandı, toplam 2 kart. Mesajlar arası 1 sn bekleme var (`tur.py:90-96`). |
| E4 eşzamanlı turda çift kart | **kapandı** | Gerçek süreçler arası `flock` denendi (yukarıda). launchd aynı işi zaten üst üste başlatmıyor; kilit elle `--force` çakışmasını kapatıyor. `run_tur`'u doğrudan iki bağlantıyla çağırmak hâlâ çift üretir (R9: 4 kart) ama bu yol yalnız CLI'dan geçiyor. |
| Ö1 özetten geri alınca ikinci kart | **kapandı** | R3: `aynı mail için gönderilen kart sayısı: 1 | ilk kart id 102 yeni kart id 102` (mevcut kart düzenlendi). |
| Ö2 20'den fazla otomatik işlemde düğme eksik | **kapandı** | R4: 25 otomatik işlem → 2 özet mesajı (20 + 5 düğme); test 20+2'yi ve parça parça telafiyi doğruluyor. |
| Ö3 dinleyici hesap/izin değişimini görmüyor | **kapandı** | Gerçek `cmd_dinle` kapanışıyla: `1. basış: Gmail'e ulaşılamadı…`, `2. basış: 🗑 Çöpe atıldı`, kurulumlar `[['a'], ['a']]`, yeni hesap sonrası `['b']` kuruldu. |
| Ö5 Gmail'de yeniden deneme yok | **kapandı** | Bütün `.execute(num_retries=3)` (`gmail.py` farkı). `googleapiclient.http` logları kapatıldı (`cli.py:19`). |
| Ö6 boş gönderene kural | **kapandı** | `rule_for('')` → `None`, otomatik işlem yok. |
| Ö7 plist'te HOME | **kapandı** | Üretilmiş iki plist'te `"HOME" => "/Users/oguzhan"`, lint OK. |
| Ö9 bot-kur onaysız sohbet | **kapandı** | Kod: yalnız `/start` metinli mesajlar aday, ad/kullanıcı adı/kimlik gösteriliyor, `evet` yazılmadan Anahtar Zinciri'ne ve ayara yazılmıyor (`cli.py:102-121`); testler evet/hayır/boş/yes durumlarını kapsıyor. |
| Ö4, Ö8, Ö10 | açık (kullanıcı kararıyla kapsam dışı) | Ö8 şimdi biraz daha geçerli: her 15 dakikada `tur: {'skipped': True}` satırı iki loga yazılıyor (biri dönmüyor). |

## Yeni sorunlar

### Engel

#### Y1. Bir hesap bozuksa tur hiç "tamamlandı" sayılmıyor; 15 dakikada bir uyarı ve kart dağıtımı, süresiz

- **Yer:** `mail_ajani/tur.py:27` (`complete = not warnings`: istemcisi kurulamayan hesap), `tur.py:40` (çekim hatası → `complete = False`),
  `tur.py:19-20` (`tur_incomplete == "1"` iken `should_run` atlanıyor), plist'teki `StartInterval=900`.
- **Tetikleyici:** Bir hesabın izni düşer (spec'e göre kişisel Gmail haftada bir yeniden izin isteyebilir) ya da bir hesabın çekimi sürekli
  hata verir. Hesap düzeltilene kadar sürer.
- **Etki:** Her 15 dakikada (gece 08:00'e kadar sessiz, sonra sesli) aynı "⚠️ Uyarı" mesajı gider: günde ~96 bildirim. Sağlam hesaplara
  gelen yeni mailler günde 4 kez yerine 15 dakikada bir özet + kart olarak dağıtılır (spec: "günde 4 kez"). `last_run` hiç ilerlemez.
  Mail kaybı ya da çift kart yok; sorun gürültü ve sözleşme bozulması.
- **Kanıt (N1/N2, çalıştırıldı):** hesap `a` için istemci uyarısı, hesap `b` sağlam:
  ```
  12:00 {'new': 0, ..., 'warnings': 1, 'incomplete': True}
  12:15 {'new': 0, ..., 'warnings': 1, 'incomplete': True}
  12:30 {'new': 1, 'auto': 0, 'cards': 1, 'warnings': 1, 'incomplete': True}
  12:45 ... 13:00 {'new': 1, ..., 'incomplete': True} ... 13:15 ...
  toplam telegram mesajı: 10 | uyarı mesajı: 6 | özet: 2 | last_run: None
  ```
  Sürekli çekim hatasında (N2) aynısı: 3 çağrıda 3 uyarı. Bu davranış `tests/test_tur.py::test_missing_client_keeps_slot_open` ile istenen
  davranış olarak test altına alınmış.
- **Düzeltme:** Hesap hataları dilimi açık tutmasın: `last_fetch:<hesap>` zaten ilerlemediği için o hesabın mailleri sonraki turda
  kayıpsız gelir (tur 1'de doğrulanan davranış). Dilimi yalnız Telegram teslimi yarım kaldığında açık bırak (`complete`'i sadece
  `TelegramError` dalında `False` yap; `tur.py:27` ve `tur.py:40`'taki atamaları kaldır).

### Öneriler

#### Y2. Kalıcı olarak reddedilen tek bir kart, arkasındaki bütün kartları ve uyarıları süresiz bekletiyor; her denemede özet yeniden gidiyor
- **Yer:** `mail_ajani/tur.py:114-118` (kartlar sırayla, ilk hatada döngü kırılıyor), `telegram.py:61-62` (400 tekrar edilmiyor, doğru).
- **Tetikleyici:** Telegram'ın kalıcı 400 verdiği bir kart; en olası örnek 4096 karakteri aşan kart metni (konu başlığı uzunluk sınırı
  yok, `render.py:13-21`).
- **Etki:** O karttan sonra sıralanan kartlar ve uyarı mesajı hiç gitmez; dilim açık kaldığı için 15 dakikada bir yeniden denenir, her
  seferinde özet mesajı tekrar gelir, kalan mailler her seferinde yeniden sınıflandırılır (Claude çağrısı). Eski kodda da aynı mail turu
  kilitliyordu (6 saatte bir); yeni sürüm bunu 15 dakikalık özet tekrarına çeviriyor.
- **Kanıt (N3, çalıştırıldı):** 3 mail, ortadakinin konusu 5000 karakter, sahte Telegram o kartı reddediyor:
  `özet sayısı: 4 | 'sonraki' kartı gitti mi: False | uyarı gitti mi: False` (12:00-12:45, her çağrı `incomplete`).
- **Düzeltme:** Kart metnini (konu ve ad) Telegram sınırının altında kes; 400 alan kartı atlayıp sonrakilere devam et ve o maili kartsız
  uyarıyla bildir.

#### Y3. Atlanan 15 dakikalık çağrılar bile Anahtar Zinciri'ni okuyor ve Gmail jetonlarını yeniliyor
- **Yer:** `mail_ajani/cli.py:49-57`: `_telegram` (Anahtar Zinciri) ve `build_clients` (her hesap için Anahtar Zinciri + gerekirse jeton
  yenileme, ağ) `run_tur`'un atlama kararından (`tur.py:19-21`) **önce** çalışıyor.
- **Etki:** Günde 96 kez gereksiz Anahtar Zinciri erişimi ve saatte bir jeton yenileme. Tur 1 açık soru 3'teki Anahtar Zinciri izin penceresi
  çıkarsa her 15 dakikada bir çıkar.
- **Düzeltme:** `cmd_tur`'da veritabanını açıp `should_run`/`tur_incomplete`/`telegram_retry_at` denetimini sırlar ve istemcilerden önce yap.

#### Y4. Sınıflandırıcı artık tek bir eksik/hatalı öğede bütün 25'lik parçayı tahminsiz bırakıyor
- **Yer:** `mail_ajani/classifier.py:73-80` (`geçersiz mail sonucu`, `eksik mail sonucu`).
- **Etki:** Güvenli tarafta (mailler tahminsiz kart olarak gider) ama Sonnet 25 mailden birini atlarsa 24 doğru tahmin de atılır ve tarz
  öğrenmesi o turda veri kaybeder. Eski test bu durumu ("uydurma" kararlı öğe atlanır, diğerleri kalır) bekliyordu; yeni test kaldırıp yerine
  "bütün parça düşer"i koydu (`tests/test_classifier.py:22-26`). Bu bilinçli bir tasarım değişikliği, güvenliği zayıflatmıyor.
- **Düzeltme:** Biçimi bozuk dış çıktıda parçayı düşür; tek tek eksik ya da geçersiz öğede yalnız o maili tahminsiz bırak.

#### Y5. Belirsiz ağ hatasında `sendMessage` tekrarı çift kart üretebilir
- **Yer:** `mail_ajani/telegram.py:56-58` (`ConnectionError`/`Timeout` için tekrar).
- **Etki:** İstek Telegram'a ulaşıp cevap yolda kaybolursa (okuma zaman aşımı, bağlantı sıfırlanması) aynı kart iki kez gider. Kanıt:
  `readtimeout sonra ok: ok 9 | deneme=2` (ilk denemenin teslim edilip edilmediği istemciden bilinemez). Düzeltme raporu bu sınırı
  zaten açıkça yazmış; tekrar olmasa da dilim tekrarı aynı sonucu doğururdu. Kabul edilebilir, bilinçli karar olarak kalsın.

#### Y6. Yarım dilimin her devamında özet yeniden gidiyor
- **Yer:** `mail_ajani/render.py:57-58` (`summary_batches([])` → `[[]]`), `tur.py:107-109`.
- **Etki:** R5 ve N5'te devam çağrısı önce yeni bir "N yeni" özeti, sonra kalan kartları yolluyor. Kayıp/çift kart yok, küçük gürültü.
- **Düzeltme:** Devam turunda (önceki deneme yarım kaldıysa ve yeni otomatik işlem yoksa) özet yerine yalnız kalan kartları gönder.

## Testler: 77'den 154'e artış meşru mu

Evet. `git show HEAD:` ile karşılaştırma: test fonksiyonu sayısı 77 → 108 (+31 yeni fonksiyon: `test_tur.py` 11 → 26, `test_cli.py` 2 → 8,
`test_telegram.py` 5 → 9, `test_dinleyici.py` 10 → 13, `test_classifier.py` 7 → 10, `test_gmail.py` 7 → 9, yeni `test_launchd.py` 2, `test_db.py`
ve `test_learning.py` +1). Kalan 46'lık fark parametreli testlerden geliyor (toplam 49 parametre örneği; ör. bozuk Claude çıktısı için 20
örnek). Hiçbir test dosyası ya da güvenlik testi silinmemiş. Değişen eski iddialar:

- `test_db.py`: `pending_excludes_sent_and_decided` → otomatik kararlı mail artık bekleyenlerde (E1'in gereği); kullanıcı kararlı mailin
  elendiği yeni bir iddiayla güçlendirilmiş.
- `test_classifier.py`: ham CLI metni ("rate limit") artık uyarıda beklenmiyor, tersine yokluğu doğrulanıyor; "uydurma" öğesinin atlanması
  yerine bütün parçanın düşmesi bekleniyor (bkz. Y4).
- `test_render.py`: "2 tane daha" yerine 22 düğmenin hepsi ve 20+2 parçalama bekleniyor (daha sıkı).
- `test_telegram.py`: Telegram'ın açıklama metni yerine Türkçe sabit metin; ağ hatası testi 4 denemenin tükenmesini bekliyor (tekrar eklendiği için).
- `test_tur.py::test_account_failure_warns_and_others_continue`: ham hata metni yerine sınıf adı; ek olarak `last_run is None` bekleniyor.
  Bu son iddia Y1'deki hatalı davranışı sabitliyor; Y1 düzeltilince değiştirilmeli.
- `conftest.py`: `tur.sleep` ve `telegram.sleep` bütün testlerde etkisiz (testler hızlı kalsın diye). Bekleme süreleri ayrı testlerde
  kayıtla doğrulanıyor; bu bir iddia zayıflatması değil.

## launchd

İki plist de geçerli (`plutil -lint` hem şablonda hem `kur.sh` dönüşümünden sonra OK). Tur: 00/06/12/18 takvimi, `StartInterval=900`,
`RunAtLoad`, `HOME` ve `PATH`. Dinleyici: `KeepAlive`, `RunAtLoad`, `HOME`, `PATH`. Tamamlanmış dilimde 15 dakikalık çağrılar hiçbir
şey göndermiyor (N4: 12:15, 12:30, 17:45 atlandı, 18:00 çalıştı, 18:15 atlandı). Sorunlar Y1 (bozuk hesapta döngü) ve Y3 (atlanan
çağrının bile sır okuması). Plist değişiklikleri yüklü ajanlara ancak `scripts/kur.sh` yeniden çalışınca uygulanır.

## Tur 1 açık soruları

Hepsi açık; bu turda değişmedi (konuşma mı mesaj mı arşivi, `untrash`'ın gelen kutusuna döndürmesi, launchd altında Anahtar Zinciri izni,
`after:` örtüşmesi, yıldızlı gönderen tanımı, Claude çıktısının launchd altında doğrulanması, gönderim ile kayıt arası çökme penceresi).
Canlı denemede ilk ikisi ve Anahtar Zinciri izni özellikle bakılmalı.
