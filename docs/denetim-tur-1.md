# Mail Ajanı: bağımsız denetim, tur 1

Tarih: 5 Ekim 2026 · Denetleyen: Opus (salt okunur) · Kapsam: `mail_ajani/`, `launchd/`, `scripts/`, `tests/`
Doğruluk kaynağı: `docs/specs/2026-09-19-mail-ajani-design.md`. Plan metnine değil, depodaki gerçek dosyalara bakıldı.

## Kısa sonuç

Temel güvenlik çizgileri yerinde: kalıcı silme yok, okunma durumu değişmiyor, eşikler doğru (10 ardışık aynı karar; son 30'da en az 29),
yıldızlı gönderen engeli ve geri al ile güven sıfırlama çalışıyor, yalnız sahibin sohbet kimliği kabul ediliyor, Telegram anahtarı hata ve
loglara sızmıyor. Gerçek hesaplara bağlanmadan önce düzeltilmesi gereken **4 engel** var. Dördü de "bir şey ters gidince sessizce
yanlış davranma" türünden: otomatik işlem yapılıp bildirimi kayboluyor, beklenmeyen Claude çıktısı bütün turu sessizce çökertiyor,
Telegram hatası turu yarıda kesip 6 saat susuyor, iki tur aynı anda çalışırsa kartlar çift gidiyor. Hepsinin düzeltmesi küçük.

## Çalıştırılan kontroller ve sonuçları

| Kontrol | Sonuç |
|---|---|
| `MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q` | geçti (77 passed) |
| `plutil -lint launchd/*.plist` | geçti |
| `kur.sh`'deki `sed` dönüşümüyle plist'leri geçici klasöre üretip `plutil -lint` + `plutil -p` (yol, saat 00/06/12/18, RunAtLoad, log yolları) | geçti |
| `bash -n scripts/kur.sh scripts/kaldir.sh` | geçti |
| launchd benzeri boş ortamda (`env -i HOME=… PATH=/usr/bin:/bin`) paket ve bağımlılık içe aktarma, keyring arka ucu | geçti (`keyring.backends.macOS`) |
| Boş ortamda Python metin kodlaması (Türkçe stdin/stdout için) | geçti (`utf-8`, UTF-8 modu açık) |
| `.venv/bin/python` bağı | sabit `/opt/homebrew/opt/python@3.14` yoluna bağlı; 3.14.x yükseltmesinde kırılmaz |
| `grep` ile `messages.delete`, `batchDelete`, `UNREAD`, `threads(` taraması | geçti (hiçbiri yok) |
| Çalışma ağacında anahtar deseni taraması (Telegram anahtarı, `ya29.`, `1//0…`, `GOCSPX`, `refresh_token`) | geçti (bulunmadı) |
| Telegram ağ hatasında dinleyici logunda anahtar var mı (sahte oturum, `log.exception` dahil) | geçti (sızmıyor) |
| Gerçek `requests` + urllib3 ile INFO ve DEBUG seviyesinde yerel kapalı porta istek, logda anahtar | geçti (sızmıyor) |
| Yeniden üretimler R1, R2, R3, R4, R5, R9 ve boş gönderen denemesi (geçici betikler, bellek içi ya da geçici klasördeki veritabanı, sahte Gmail/Telegram) | 7 sorun doğrulandı |
| Gerçek Gmail, Telegram, `claude` CLI, launchd yükleme, Anahtar Zinciri okuma | çalıştırılmadı (kapsam dışı) |

---

## Engeller (gerçek hesaplara bağlamadan önce düzeltilmeli)

### E1. Otomatik karar Telegram'a ulaşmadan kaydediliyor; Telegram hatasında "önemli" kartı ve geri al düğmesi sonsuza dek kayboluyor

- **Yer:** `mail_ajani/tur.py:47-59` (Gmail'e uygula + `db.add_decision` + `mark_sent(None)`), gönderim ancak `tur.py:63-75`'te.
- **Tetikleyici:** Bir kural ya da tarz yetkisi açıldıktan sonra, turun özet veya kart gönderimi sırasında Telegram hatası (ağ kopması, 429).
  Sık yazan bir bildirim göndericisi tek günde 10 karara ulaşabilir, yani bu durum ilk günlerde açılabilir.
- **Etki:** Otomatik "önemli" kararı alınmış mail Gmail'de yıldızlanır ama kartı hiç gelmez (spec: "Önemli otomatik kararında ajan
  yalnız işaretler ve Telegram'a gönderir"). Otomatik çöp/arşiv yapılan mailler özette hiç listelenmez, **Geri al** düğmesi hiç gelmez;
  Oğuzhan çöpe giden maili fark etmez. Mailin etkin kararı olduğu için `pending_mails` onu bir daha seçmez.
- **Kanıt (R1, çalıştırıldı):** 10 kez ⭐ verilmiş gönderenden yeni mail; Telegram `send` hata veriyor.
  ```
  run 1 crashed: TelegramError: sendMessage: bağlantı hatası
  gmail applied: [('g901', 'onemli')]
  run 2: {'new': 0, 'auto': 0, 'cards': 0, 'warnings': 0}
  run 2 telegram messages: 0
  pending: 0 | mail sent_at: None
  ```
- **Düzeltme:** Otomatik kararlı mailleri, özet (ve önemliyse kart) başarıyla gönderilene kadar "bildirilmedi" say (ör. `sent_at` NULL kalsın ve
  bekleyen sorgusu "etkin otomatik kararı olup bildirilmemiş" mailleri de getirsin; bunlar yeniden uygulanmadan yalnız özete ve karta girsin).
  `mark_sent` yalnız Telegram başarılı olduktan sonra çağrılsın.

### E2. Beklenmeyen Claude çıktısı `classify`'dan dışarı taşıyor; tur sessizce çöküyor, hiçbir mail gelmiyor

- **Yer:** `mail_ajani/classifier.py:47-66` (`outer.get`, `data.get("items", [])`, `item.get`), yakalama yalnız
  `classifier.py:84`: `except (ClassifierError, subprocess.TimeoutExpired, OSError)`. `tur.py:34`'te de koruma yok.
- **Tetikleyici:** `claude` çıktısının biçimi değişirse (CLI kendini otomatik güncelliyor: `~/.local/bin/claude -> …/versions/2.1.289`),
  JSON dizi/metin dönerse, `items` null ya da öğeler nesne değilse.
- **Etki:** Plan "Never raises" diyor, spec "Sonnet çağrısı başarısız olursa mailler tahminsiz, düğmeli gelir" diyor. Gerçekte `run_tur`
  çöküyor: kart yok, uyarı yok, `last_run` yazılmıyor. Çıktı biçimi kalıcı değiştiyse **her tur** sessizce çöker; Oğuzhan mail almadığını
  fark etmeden günler geçebilir.
- **Kanıt (R2, çalıştırıldı):**
  ```
  '[]' -> KAÇAN HATA AttributeError 'list' object has no attribute 'get'
  '"metin"' -> KAÇAN HATA AttributeError 'str' object has no attribute 'get'
  '{"structured_output": {"items": null}}' -> KAÇAN HATA TypeError 'NoneType' object is not iterable
  '{"structured_output": {"items": ["x"]}}' -> KAÇAN HATA AttributeError 'str' object has no attribute 'get'
  run_tur crashed: AttributeError
  telegram: 0 last_run: None pending: 1
  ```
- **Düzeltme:** `classify` içinde parça başına `except Exception` ile hatayı `errors` listesine yaz (ve `parse_output`'ta `outer`, `items`,
  her öğe için tür denetimi yap); `tur.py:34`'teki çağrıyı da `try/except Exception` ile sar ki sınıflandırıcıda ne olursa olsun kartlar gitsin.

### E3. Telegram hatası (429 dahil) turu yarıda kesiyor; uyarı gitmiyor, kalan mailler 6 saat bekliyor; ilk turda hız sınırı riski yüksek

- **Yer:** `mail_ajani/tur.py:71-73` (kartlar arka arkaya, bekleme yok), `mail_ajani/telegram.py:20-21` (`retry_after` okunmuyor, yeniden deneme yok),
  `mail_ajani/cli.py:46` (`run_tur` korumasız), `launchd/com.oguzhan.mail-ajani.tur.plist:11-18` (yalnız 4 sabit saat + RunAtLoad).
- **Tetikleyici:** İlk tur 3 hesap × 24 saat geriye bakar ve onlarca kartı tek sohbete art arda yollar; Telegram tek sohbete hızlı ardışık
  gönderimde 429 "Too Many Requests: retry after N" döner. Ya da o anda kısa bir ağ kopması.
- **Etki:** Mail kaybolmaz ama tur kalan kartları göndermeden çöker, uyarı gönderilmez, `last_run` yazılmaz. launchd işi yeniden denemez;
  sonraki deneme bir sonraki saat dilimi (6 saate kadar). Sonraki turda özet tekrar gelir ve kalanlar yeniden sınıflandırılır.
  Telegram'da bir hata olduğunu gösteren hiçbir şey yoktur.
- **Kanıt (R5, çalıştırıldı):** 40 mail, sahte Telegram 21. mesajda 429 veriyor.
  ```
  tur 1 çöktü: TelegramError: sendMessage: Too Many Requests: retry after 7
  gönderilen: 21 | bekleyen: 20 | last_run: None
  tur 2 (6 saat sonra) özet: <b>18:00 turu</b> · 20 yeni · 0 önemli · 20 senin kararını bekliyor | kart: 20
  ```
- **Düzeltme:** `TelegramClient._call` 429'da `parameters.retry_after` kadar bekleyip birkaç kez yeniden denesin ve kartlar arasında kısa
  bekleme olsun (ör. 0,5-1 sn). Tur plist'ine `StartInterval` (ör. 900 sn) eklensin: `should_run` zaten aynı dilimi ikinci kez çalıştırmıyor,
  böylece yarıda kalan tur 15 dakika içinde kaldığı yerden devam eder.

### E4. Aynı anda iki tur çalışırsa aynı mailler iki kez kart olarak gidiyor

- **Yer:** `mail_ajani/cli.py:39-49`, `mail_ajani/tur.py:30-73` (kilit yok; `pending_mails` okuması ile `mark_sent` arasında dakikalar geçebiliyor,
  sınıflandırma parça başına 300 sn'ye kadar sürüyor).
- **Tetikleyici:** `scripts/kur.sh` RunAtLoad yüzünden kurulur kurulmaz bir tur başlatır; o tur Claude'u beklerken README'deki
  `tur --force` elle çalıştırılırsa. Canlı kurulumda bu sıra çok olası.
- **Etki:** Spec'in "bir mail asla ikinci kez gönderilmez" garantisi bozulur; her mail için iki kart, iki özet.
- **Kanıt (R9, çalıştırıldı):** aynı dosya veritabanına iki bağlantı; birinci tur sınıflandırmadayken ikinci tur çalışıyor.
  ```
  2 mail için kart sayısı: 4
  ```
- **Düzeltme:** `cmd_tur` başında `config.home()/tur.lock` üzerinde `fcntl.flock(LOCK_EX | LOCK_NB)` al; alınamazsa "başka tur çalışıyor" deyip çık.

---

## Öneriler

### Ö1. Özetten "otomatik önemli" geri alınınca aynı mail için ikinci kart gidiyor
- **Yer:** `mail_ajani/dinleyici.py:58-62`. Geri al özet mesajından basılınca, mailin zaten bir kartı (`tg_message_id`) olsa bile yeni kart gönderiliyor.
- **Etki:** Eski kart düğmeleriyle durmaya devam eder; aynı mail iki kart (küçük ama "asla ikinci kez" kuralına aykırı).
- **Kanıt (R3, çalıştırıldı):** `aynı mail için gönderilen kart sayısı: 2 | ilk kart id 102 yeni kart id 103`
- **Düzeltme:** `mail["tg_message_id"]` doluysa o kartı düzenle; yeni kartı yalnız kart hiç yoksa (otomatik çöp/arşiv) gönder.

### Ö2. Bir turda 20'den fazla otomatik işlem olursa 21. ve sonrası için Geri al düğmesi yok
- **Yer:** `mail_ajani/render.py:9`, `render.py:42-47`, `render.py:54-55` (`MAX_AUTOS_LISTED = 20`).
- **Etki:** Spec "her otomatik işlem Geri al ile gelir" diyor; fazlası yalnız "… ve N tane daha" olarak geçiyor, Telegram'dan geri alınamıyor.
- **Kanıt (R4, çalıştırıldı):** `otomatik çöp: 25 | geri al düğmesi: 20 | telegram mesajı: 1`
- **Düzeltme:** Özeti 20'lik parçalara bölüp her parçayı kendi düğmeleriyle ayrı mesaj olarak gönder.

### Ö3. Dinleyici hesap listesini ve Gmail istemcisini bir kez yüklüyor; yeni hesap ya da yenilenen izin yeniden başlatmadan görünmüyor
- **Yer:** `mail_ajani/cli.py:53` (`cfg` bir kez okunuyor), `cli.py:58-65` (istemci önbelleği hiç boşaltılmıyor).
- **Tetikleyici:** Dinleyici çalışırken `hesap-ekle` ile yeni hesap eklemek; kişisel Gmail'in haftalık yeniden izni (spec'te öngörülüyor).
- **Etki:** Yeni hesabın kartlarında "Bu hesap şu an bağlı değil"; izni yenilenen hesapta dinleyici eski (iptal edilmiş) jetonu tutmaya
  devam eder ve her düğmede "Gmail'e ulaşılamadı" der, dinleyici yeniden başlatılana kadar. Tur etkilenmez (her turda yeniden kurar).
- **Kanıt:** kod okuması (`get_clients` yalnız `cfg["accounts"]` içinde olup önbellekte olmayanları kurar; önbellekten çıkarma yok).
- **Düzeltme:** Bilinmeyen hesapta ayarı yeniden oku; Gmail işleminde yetki hatası (401 / `RefreshError`) gelirse o hesabı önbellekten
  sil ki sonraki basışta Anahtar Zinciri'nden yeniden kurulsun. Kısa vadede: her `hesap-ekle`'den sonra `scripts/kur.sh` çalıştırılsın.

### Ö4. `/durum` "hata var mı" bilgisini göstermiyor
- **Yer:** `mail_ajani/dinleyici.py:92-95`, `render.py:81-84`. Spec: "`/durum` (son tur, hata var mı)".
- **Etki:** E2/E3 gibi çökmeler Telegram'dan görülemez; tek ipucu "Son tur" tarihinin eskimesi.
- **Düzeltme:** Tur başında `last_attempt`, sonunda uyarı/hata özetini `meta`'ya yaz; `/durum` bunları ve "son tur 6 saatten eski" uyarısını göstersin.

### Ö5. Gmail çağrılarında geçici hatalar için yeniden deneme yok
- **Yer:** `mail_ajani/gmail.py:30, 34-35, 43, 50-51, 65-82` (`.execute()` hep `num_retries=0`).
- **Etki:** Tek bir 429/5xx bütün hesabın o turdaki çekimini düşürür (uyarı + bir sonraki tura kalır) ya da dinleyicide "tekrar dene" der.
  Mail kaybı yok, gürültü ve gecikme var.
- **Düzeltme:** `.execute(num_retries=3)` kullan (googleapiclient 429/5xx için üstel bekleme yapıyor).

### Ö6. Boş gönderen adresi için kural oluşabiliyor
- **Yer:** `mail_ajani/gmail.py:53-57` (`parseaddr` boş adres döndürebilir), `mail_ajani/learning.py:20-33`.
- **Etki:** `From` başlığı bozuk/boş maillere 10 kez çöp denirse "" gönderenine kural açılır ve sonraki bütün bozuk `From`'lu mailler
  (aralarında gerçek olanlar da olabilir) otomatik çöpe gider.
- **Kanıt (çalıştırıldı):** `parseaddr('')`, `parseaddr('undisclosed-recipients:;')`, `parseaddr('Bank <>')` hepsi boş adres veriyor;
  10 karardan sonra `rule_for(conn, '') == 'cop'`.
- **Düzeltme:** Gönderen boşsa kural oluşturma ve otomatik işlem yapma (her zaman kart).

### Ö7. launchd ortamına `HOME` açıkça yazılsın
- **Yer:** `launchd/*.plist:9-10` yalnız `PATH` veriyor.
- **Etki:** launchd kullanıcı ajanlarına `HOME`'u normalde kendisi veriyor ve Python/`claude` yoksa parola kaydına düşüyor; yine de
  `launchctl print` çıktısında görünmüyor (mevcut bir ajanda denendi). Bedava bir güvence.
- **Düzeltme:** `EnvironmentVariables`'a `<key>HOME</key><string>__HOME__</string>` ekle (isteğe bağlı `LANG=en_US.UTF-8`).

### Ö8. Log çoğalması ve yeniden başlama döngüsü
- **Yer:** `mail_ajani/cli.py:16` (`StreamHandler` + plist'teki `StandardErrorPath`): her satır hem dönen `tur.log`'a hem dönmeyen
  `tur.launchd.log`'a yazılıyor; ikincisi sınırsız büyür. `cli.py:54-56` + dinleyici plist `KeepAlive`: Telegram kurulmadan dinleyici
  yüklenirse 30 sn'de bir çıkıp yeniden başlar.
- **Düzeltme:** launchd altında (`not sys.stderr.isatty()`) `StreamHandler`'ı ekleme; dinleyici kurulu değilse uzun bir `sleep` ile beklesin
  ya da `kur.sh` Telegram ve hesap kurulmadan çalışmayı reddetsin. Ayrıca `logging.getLogger("urllib3").setLevel(logging.WARNING)`
  ile ileride DEBUG açılırsa anahtarlı URL'nin loga düşmesi baştan engellensin.

### Ö9. `bot-kur` son mesaj atanın sohbetini sahip olarak kaydediyor, kime ait olduğunu göstermiyor
- **Yer:** `mail_ajani/cli.py:87-94` (`chats[-1]`).
- **Etki:** Bot adı bulunabilir; kurulum anında başka biri de yazmışsa onun sohbeti "sahip" olur ve bütün mailler ona gider. Düşük olasılık, yüksek etki.
- **Düzeltme:** Bulunan sohbetin adını/kullanıcı adını yazdırıp onay iste; yalnız `/start` metinli mesajları say.

### Ö10. Canlı kurulum sırası
- `scripts/kur.sh` RunAtLoad yüzünden **hemen** bir tur çalıştırır (`last_run` boş olduğu için) ve o an ayarda kaç hesap varsa hepsinden
  24 saat geriye çeker. Spec'teki "tek hesapla bir tur" denemesi için: önce tek hesap + `bot-kur`, elle `tur --force`, düğme denemesi;
  diğer hesaplar ve `kur.sh` sonra. E4 düzelene kadar `kur.sh` sonrası elle `tur --force` çalıştırılmamalı.

---

## Açık sorular (doğrulanmadı, bulgu sayılmadı)

1. **Konuşma (thread) görünümünde arşiv/çöp:** `apply` tek mesaja uygulanıyor (`messages.modify/trash`). Aynı konuşmanın eski bir mesajı
   gelen kutusundaysa konuşma kutuda kalmaya devam eder; Oğuzhan "arşivledim ama duruyor" görebilir. Canlı denemede yanıtlı bir
   konuşmayla bakılmalı; istenen davranış "yalnız bu mesaj" mı "bütün konuşma" mı, Oğuzhan'a sorulmalı.
2. **`untrash` gelen kutusuna geri koyuyor mu:** Çöp → Geri al sonrası mailin INBOX etiketiyle döndüğü canlı denemede görülmeli
   (`gmail.py:75-76` yalnız `untrash` çağırıyor, INBOX eklemiyor).
3. **Anahtar Zinciri izni launchd altında:** jetonlar `hesap-ekle` ile terminalden yazılıyor; launchd altındaki aynı Python'un okurken izin
   penceresi açıp açmadığı ve Homebrew Python güncellemesinden sonra pencerenin yeniden çıkıp çıkmadığı bilinmiyor. Pencere açılırsa ve
   kimse başında değilse tur takılır. İlk launchd turundan sonra `tur.log` kontrol edilmeli.
4. **`after:` ve geciken mailler:** Sorgu `in:inbox after:<son çekim - 1 saat>`. Gmail'in `after:` filtresi mailin iç tarihine bakar;
   POP ile başka kutudan çekilen ya da geç teslim edilen mailin iç tarihi 1 saatten eskiyse pencereye girmeyebilir. Veritabanı tekrarları
   zaten elediği için örtüşmeyi ör. 24 saate çıkarmak ucuz bir sigorta olur.
5. **Yıldızlı gönderen tanımı:** Koruma yalnız botta ⭐'ye basılmış ve geri alınmamış kararlara bakıyor (`learning.py:9-13`). Gmail'de elle
   yıldızlanan gönderenler sayılmıyor; ⭐ kararı sonradan değiştirilirse koruma kalkıyor. Spec'teki "daha önce ⭐ verilmiş" ifadesinin
   bu anlama geldiği Oğuzhan'a teyit ettirilmeli.
6. **`claude` komut satırı:** `_command()` planın Görev 6 Adım 1'deki yakalama komutuyla aynı bayrakları kullanıyor ve
   `tests/fixtures/claude_ok.json` temiz tek JSON nesnesi (`structured_output` dolu). Fixture'ın bu komutla üretildiği plana göre doğru
   kabul edildi; CLI çalıştırılmadığı için launchd altında da aynı çıktının geldiği doğrulanmadı.
7. **Gönderim ile işaretleme arası çökme:** `tg.send` başarılı olup `mark_sent`'ten önce süreç ölürse o kart bir kez daha gider
   (`tur.py:72-73`). Pencere milisaniyeler; "en fazla bir kez" yerine "en az bir kez" tercihi olarak kabul edilebilir, bilinçli karar olarak not edilsin.

---

## Doğrulanan, sorun bulunmayan noktalar

- Kalıcı silme yok; en sert işlem `messages.trash` (`gmail.py:65`), test de `delete`'in çağrılmadığını doğruluyor.
- Okunma durumuna hiç dokunulmuyor (`UNREAD` hiçbir yerde yok; `messages.get` okundu yapmaz).
- Eşikler: kural için son 10 kullanıcı kararı aynı ve `kalsin` değil (`learning.py:20-33`); tarz yetkisi için tam 30 karar ve en az 29 doğru
  (`learning.py:49-59`); geri al kuralı siliyor ve sayacı sıfırlıyor, tarz yetkisini kapatıyor (`learning.py:81-91`); `/kurallar`'dan silme aynı yolu izliyor.
- Yıldızlı gönderen hem kural hem tarz yolunda çöp/arşivden korunuyor (`learning.py:16-17, 42-46, 66`).
- Bir hesabın çekimi düşerse diğerleri devam ediyor, o hesabın `last_fetch`'i ilerlemiyor, uyarı gidiyor (`tur.py:20-28`); çekim liste olarak
  döndüğü için yarım yazım yok. Örtüşen pencereler `UNIQUE(account, gmail_id)` ile eleniyor.
- Normal sınıflandırıcı hatalarında (çıkış kodu, zaman aşımı, bozuk JSON, `is_error`) mailler tahminsiz kart olarak gidiyor.
- Gmail sayfalama `nextPageToken` ile; `pageToken=None` istemci kütüphanesinde düşürülüyor (`discovery.py:1109-1113` doğrulandı).
  HTTP zaman aşımı kütüphane varsayılanı 60 sn (`googleapiclient/http.py:75`).
- Etiketler adla bulunuyor, yoksa bir kez oluşturuluyor; yenilenen jeton Anahtar Zinciri'ne geri yazılıyor (`gmail.py:94-99`).
- Dinleyici: yalnız sahibin sohbet kimliği; aynı düğmeye ikinci basış işlem yapmıyor; işlem değiştirmek önce eskisini geri alıyor; ofset her
  güncellemeden sonra kalıcı (çökmeden sonra tekrar işlenen basış da etkisiz kalıyor).
- Telegram hata metninde URL/anahtar yok (`telegram.py:16-21`, `from None`); dinleyici logunda da yok (çalıştırıldı).
- Saatler 00/06/12/18, gece turları sessiz, kaçırılan dilim `should_run` ile telafi ediliyor; uyku sonrası launchd takvim olaylarını birleştirip çalıştırır.

## Test boşlukları (gerçek riski gizleyenler)

- `classify`'ın "asla hata fırlatmaz" sözleşmesini sınayan test yok (E2).
- Tur sırasında Telegram hatası, otomatik kararların bildirimi ve sonraki turda telafi senaryosu test edilmiyor (E1, E3).
- Eşzamanlı tur / kilit testi yok (E4).
- Özetten geri al sonrası kart sayısı (Ö1) ve 20'den fazla otomatik işlem (Ö2) test edilmiyor.
- Dinleyicide hesap/izin değişimi sonrası davranış test edilmiyor (Ö3).
- `load_credentials` (yenileme + Anahtar Zinciri'ne geri yazma, `RefreshError` → `GmailAuthError`) ve `build_clients`'in gerçek
  `TransportError` (uykudan uyanınca ağ yok) davranışı test edilmiyor; bu durumda uyarı metni yanlış biçimde "yeniden izin ver" diyor (`cli.py:26-27`).
