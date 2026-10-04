# Mail Ajanı: bağımsız denetim, tur 3 (son doğrulama)

Tarih: 5 Ekim 2026 · Denetleyen: Opus (salt okunur) · Konu: commit edilmemiş ağaç (tur 1 + tur 2 düzeltmeleri),
[düzeltme raporu 2](duzeltme-tur-2.md), [tur 2 denetimi](denetim-tur-2.md).

## Karar

**Evet, gözetimli canlı kuruluma hazır.** Tur 2 engeli Y1 kapandı. Y3, Y4 ve Y6 kapandı. Y2 kısmen kapandı: tek bozuk kart artık diğerlerini
bekletmiyor, kendini tekrarlamıyor ve mail Gmail'de dokunulmadan duruyor. Yine de iki zayıf nokta kaldı (aşağıda Ö-A, Ö-B). Mail kaybı,
çift Gmail işlemi, çift kart ya da sır sızıntısı üreten bir yol bulmadım. Ö-A ve Ö-B, sistem gözetimsiz bırakılmadan önce düzeltilmeli;
bağlamayı engellemiyor.

## Çalıştırılan kontroller ve sonuçları

| Kontrol | Sonuç |
|---|---|
| `MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q` | geçti (188 passed) |
| Tur 1 yeniden üretimleri R1, R2, R3, R4, R5, R9 | R1-R5 doğru; R9 `run_tur` seviyesinde çift (beklenen, kilit CLI'da) |
| Tur 2 senaryoları N1-N5 | N1, N2, N4, N5 doğru; N3 sahte Telegram'ı kalıcı kod (400) taşımadığı için geçici sayıldı, aşağıda gerçek 400 ile yeniden yapıldı |
| Yeni senaryolar: Y1 telafi, Y1 çok dilim, Y2 gerçek 400, Y2 uzun alan, Y2 genel kalıcı hata (Y2c) | Y1 doğru; Y2 tek kartta doğru; Y2c sorun gösterdi (Ö-A) |
| Y3: gerçek `cli.main(['tur'])`; Anahtar Zinciri, ayar ve Gmail kurucusu çağrılırsa hata fırlatacak şekilde değiştirildi | geçti: tamamlanmış dilimde ve dolmamış `telegram_retry_at` varken hiç çağrı yok; yeni dilimde çağrılıyor (doğru) |
| Y4: gerçek `classify`, sahte çalıştırıcı | geçti (aşağıda) |
| Kilit: ayrı süreç `tur.lock`'u tutarken `python -m mail_ajani tur --force` | geçti ("Başka bir tur çalışıyor", çıkış 0) |
| Gerçek `TelegramClient` yeniden deneme sınırları ve `permanent` bayrağı (sahte HTTP oturumu) | geçti: 429 kısa → 1 tekrar; 429 600 sn → tekrar yok; 5xx/bağlantı → 4 deneme [1, 2, 4]; 400/403/407 → tekrar yok, kalıcı; hata metninde anahtar/URL yok |
| `plutil -lint launchd/*.plist`, `bash -n scripts/kur.sh scripts/kaldir.sh` | geçti; plist ve betikler tur 2'den beri değişmemiş |
| `mail_ajani/` içinde `.delete(`, `batchDelete`, `UNREAD`, `threads(` | yok (geçti) |
| HEAD'e göre silinen test satırları ve test sayısı dökümü | meşru (aşağıda) |
| Gerçek Gmail, Telegram, `claude`, launchd yükleme, Anahtar Zinciri | çalıştırılmadı (kapsam dışı) |

## Tur 2 bulgularının durumu

| Bulgu | Durum | Kanıt |
|---|---|---|
| **Y1** bozuk hesap dilimi açık tutuyor | **kapandı** | N1: `12:00 {..., 'warnings': 1}`, ardından 12:15-13:15 hep `{'skipped': True}`; `toplam telegram mesajı: 1 | uyarı mesajı: 1`, `last_run` yazıldı. N2 (sürekli çekim hatası): 3 çağrıda 1 uyarı. Telafi senaryosu: `a` 12:00'de çekemiyor, `b` sağlam; 12:15 ve 12:30 atlandı, 18:00'de `a` yine 05:00'ten (`last_fetch` 06:00 - 1 sa) çekti: `a-ARADA kart sayısı: 1`, `b-2: 1`, `b-3: 1`. Mesaj sırası `özet, kart, kart | özet, kart, uyarı | özet, kart, kart`. Bozuk istemci üç dilim boyunca: `uyarı sayısı (3 dilim): 3` (dilim başına bir). |
| **Y2** kalıcı reddedilen kart diğerlerini bekletiyor | **kısmen** | Gerçek 400 (`status_code=400`) ile: `12:00 {'new': 3, ...}`, 12:15 ve 12:30 atlandı; `mesajlar: ['özet', 'kart', 'kart', 'uyarı'] | sonraki gitti: True`, zehirli mailin `sent_at`'i ancak uyarı teslim edilince doldu. Kart alanları kesiliyor: 3000 karakterlik konu/emoji gövdeli kart UTF-16'da 3848, işlem sonrası kart 3870 (< 4096). Eksik kalan: uyarı maili yalnız iç kimlikle anıyor (Ö-B) ve Telegram'ın genel kalıcı hataları da "bu kart bozuk" sayılıyor (Ö-A). |
| **Y3** atlanan çağrı sır okuyor | **kapandı** | `tamamlanmış dilim exit: 0 | sır/istemci çağrısı: 0`; `bekleme süresi dolmamış exit: 1 | çağrı: 0`; yeni dilimde sır okumaya gidiyor. Atlama kararı kilit altında, veritabanından, sır ve istemcilerden önce (`cli.py` `cmd_tur`, `tur.skip_result`). |
| **Y4** tek kötü öğe bütün parçayı düşürüyor | **kapandı** | `bir öğe bozuk: ({1: ('cop','x'), 3: ('arsiv','y')}, ['bazı mail sonuçları eksik veya geçersiz'])`; eksik öğede aynı; yinelenen kimlikte yalnız o mail düştü: `({3: ('arsiv','y')}, …)`; hiç geçerli yok: `({}, ['geçerli mail sonucu yok'])`. Tamamen bozuk çıktı (R2) hâlâ dışarı taşmıyor: `'[]' -> ({}, ['beklenmeyen dış çıktı biçimi'])` ve diğerleri. |
| **Y5** belirsiz ağ hatasında tekrar | bırakıldı (karar) | değişmedi |
| **Y6** devamda özet tekrarı | **kapandı** | R5: devam çağrısının ilk mesajı artık kart (`tur 2 … özet: 📬 <i>a</i> | kart: 20`); N3/Y2 senaryosunda `özet sayısı: 1`. |

## Gerileme denetimi

- **Tek gönderim / çift Gmail işlemi:** R1: Telegram düşükken otomatik ⭐ bir kez uygulandı (`gmail applied: [('g901', 'onemli')]`), sonraki
  turda özet + kart + uyarı geldi. N5: 429 600 sn sonrası toplam 2 kart. Y1 telafisinde her mail tek kart.
- **Kayıp:** Bozuk hesabın penceresi korunuyor (Y1). Reddedilen kart mailinin `sent_at`'i uyarı teslim edilmeden yazılmıyor.
- **Kilit:** çalışıyor (yukarıda). **Tekrar sınırları:** değişmedi, en fazla 3 tekrar ve 60 sn.
- **Sırlar:** Telegram hata metinleri sabit Türkçe; 400 açıklamasındaki anahtarlı URL hata metnine geçmedi (`tokenda=False`).
- **Dilim muhasebesi:** tamamlanmış dilimde 15 dakikalık çağrılar hiçbir şey göndermiyor (N4: 12:15, 12:30, 17:45, 18:15 atlandı, 18:00 çalıştı).

## Yeni sorunlar

### Engel

Yok.

### Öneriler

#### Ö-A. Telegram'ın genel kalıcı hatası, devam turunda bütün bekleyen mailleri kalıcı "reddedildi" yapıyor; Telegram düzelince kartlar hiç gelmiyor
- **Yer:** `mail_ajani/telegram.py:17-20` (`permanent`: 429 dışındaki bütün 4xx, JSON olmayan 4xx dahil), `mail_ajani/tur.py:158-174`
  (kart ve kısa kart kalıcı reddedilince `card_rejections`'a yazılıyor), `tur.py:142-143` (devamda özet atlandığı için ilk istek doğrudan kart).
- **Tetikleyici:** Bir tur Telegram'ın geçici hatasıyla yarım kalır (ör. 429). Devam turu çalıştığında Telegram her isteğe kalıcı görünen
  bir 4xx döner: 401 (anahtar BotFather'da yenilendi), 403 (bot engellendi), 400 "chat not found" ya da HTML dönen bir vekil/ağ filtresi
  (407/403). İki ayrı olay üst üste gelmeli, olasılık düşük.
- **Etki:** Her bekleyen mail "kart da reddedildi" diye kalıcı işaretleniyor. Telegram düzelince bu mailler için kart ve düğme hiç gelmiyor,
  yalnız "Mail #N … Gmail'den kontrol edin" uyarısı geliyor ve mailler gönderilmiş sayılıyor. Mailler Gmail'de dokunulmadan duruyor ama
  Telegram tarafında içerik ve düğme kayboluyor. Çok sayıda mail varsa uyarı mesajı da uzar: mail başına yaklaşık 150 karakter, 28 mailden
  sonra 4096'yı geçer. O durumda uyarı kalıcı reddedilir ve dilim her 15 dakikada yeniden denenir (bu son kısım çalıştırılmadı, hesap).
- **Kanıt (Y2c, çalıştırıldı):** 4 mail; 12:00'de özetten sonra 429 (600 sn); 12:15'te her istek 403; 12:30'da Telegram sağlam.
  ```
  12:15 {'new': 4, ..., 'warnings': 10, 'incomplete': True}
  card_rejections: {"1": 403, "2": 403, "3": 403, "4": 403}
  12:30 {'new': 4, ..., 'warnings': 9}
  Telegram düzelince gelenler: ['özet', 'uyarı'] | konu-2..4 kartı geldi mi: [False, False, False]
  ```
- **Düzeltme:** Kartı yalnız Telegram'ın JSON gövdeli 400 cevabında "bu kart bozuk" say (401/403/404, 407 ve JSON olmayan cevaplar geçici
  sayılsın ve dilim açık kalsın). Ya da bir kart kalıcı reddedildiğinde ret kaydını, aynı turda başka bir mesaj başarıyla gidene kadar
  kesinleştirme. Uyarı metnini de 4096'nın altında tut (fazlasını "ve N mail daha" ile özetle).

#### Ö-B. Reddedilen mail uyarıda yalnız iç kimlikle ("Mail #2") anılıyor; Oğuzhan hangi mail olduğunu bulamaz
- **Yer:** `mail_ajani/tur.py:110-112` (`rejection_warning`), `tur.py:163`.
- **Etki:** `#2` veritabanı kimliği; Telegram'da, Gmail'de ya da `/durum`'da hiçbir yerde görünmüyor. Mail Gmail'de okunmamış duruyor, yani
  kayıp yok, ama spec'in "önemliyi kaçırmamak" amacı açısından neredeyse sessiz.
- **Kanıt (Y2, çalıştırıldı):** gönderilen uyarı:
  `• Mail #2: Telegram ayrıntılı kartı reddetti; kısa kart denendi.` / `• Mail #2: kısa kart da reddedildi. Mail yerelde kayıtlı; Gmail'den kontrol edin.`
  Uyarıda gönderen ya da konu yok (`uyarıda gönderen/konu var mı: False`).
- **Düzeltme:** Uyarıya hesap, gönderen adresi ve konunun ilk ~60 karakterini ekle (`_short_html` ile kaçışlı ve kısa). Kart reddine yol açan
  alanın uyarıyı da bozmaması için düz metin ve kısa tut.

#### Ö-C. `card_rejections` kaydı hiç temizlenmiyor
- **Yer:** `mail_ajani/tur.py:42, 170-171`. Küçük bir JSON sözlüğü `meta` tablosunda süresiz büyüyor; işlevsel etkisi yok. Mail gönderildi
  sayıldıktan sonra kaydı silmek yeterli.

## Testler

- 154 → 188 (toplanan test), fonksiyon sayısı 108 → 130. Artış `test_tur.py` (26 → 34), `test_cli.py` (8 → 10), `test_telegram.py` (9 → 11),
  `test_classifier.py` (10 → 13), `test_render.py` (8 → 9) ve parametrelerden geliyor. Yeni testler Y1-Y6 senaryolarını kapsıyor.
- HEAD'e göre silinen satırlar tur 2'de incelenen listeyle **aynı**; bu turda HEAD'den gelen başka bir iddia silinmedi.
- Tamamen bozuk Claude çıktısı için 20 örneklik parametreli test aynen duruyor (`tests/test_classifier.py:80-104`), "hiç sızmaz" iddiasıyla.
- Tur 2'de Y1'in hatalı davranışını sabitleyen iki iddia (`test_missing_client_keeps_slot_open` ve hesap hatasında `last_run is None`) yeni
  sözleşmeye göre değiştirilmiş: şimdi dilimin kapandığını, ara çağrıların atlandığını ve sonraki dilimde telafiyi doğruluyorlar. Bu
  zayıflatma değil, düzeltme.
- Test boşluğu: Ö-A senaryosu (devamda genel 401/403) ve uyarı mesajının 4096 sınırı test edilmiyor.

## Açık kalanlar

Kullanıcı kararıyla Ö4 (`/durum`'da hata), Ö8 (log çoğalması), Ö10 (kurulum sırası notu), Y5 ve tur 1'in yedi açık sorusu duruyor. Canlı
denemede özellikle bakılmalı:

- konuşma görünümünde tek mesaj arşivlenince konuşmanın gelen kutusunda kalıp kalmadığı,
- `untrash`'ın maili gelen kutusuna geri koyup koymadığı,
- launchd altında Anahtar Zinciri izin penceresi.

Plist değişiklikleri (`StartInterval=900`, `HOME`) ancak `scripts/kur.sh` yeniden çalışınca yüklü ajanlara geçer.
