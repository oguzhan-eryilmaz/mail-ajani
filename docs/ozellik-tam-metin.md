# Otomatik önemli maillerin tam metni

5 Ekim 2026

Otomatik kararın işlemi `onemli`, kaynağı `rule` veya `style` olduğunda, mevcut
özetli ve düğmeli kartın hemen ardından mailin okunabilir tam metni gönderiliyor.
Yalnızca önemli tahmini bulunan kartlar ve sahibinin düğmeyle önemli işaretlediği
mailler bu gönderimi başlatmıyor. Kartın metni, düğmeleri ve düzenleme işlevleri
korundu.

## Uygulama

`GmailClient.fetch_body(gmail_id)` tek bir `messages.get(format="full")` çağrısını
`num_retries=3` ile çalıştırıyor. MIME ağacındaki dosya adı bulunan ekler ve ek alt
ağaçları atlanıyor; okunabilir düz metin tercih ediliyor. Düz metin bulunamazsa
HTML, yalnız Python standart kütüphanesiyle okunabilir metne çevriliyor: script ve
style içeriği kaldırılıyor, blok sonları ve `<br>` satır sonuna dönüşüyor, HTML
karakter varlıkları çözülüyor. Base64url verisi, parçanın charset bilgisiyle ve
`errors="replace"` ile çözülüyor; eksik veya tanınmayan charset için UTF-8
kullanılıyor. Satır sonu boşlukları ve fazla boş satırlar temizleniyor.

Takip mesajları `📄 Tam metin · <kısaltılmış konu>` başlığıyla geliyor. Birden çok
parça varsa `(1/3)`, `(2/3)` gibi numaralanıyor. Konu ve gövde HTML için kaçırılıyor;
`render._short_html` ile aynı kaçırılmış UTF-16 uzunluk hesabı kullanılıyor.
Başlık ve parça numarası dahil her mesaj en fazla 4095 UTF-16 birimi. Bir mail için
en fazla dört takip mesajı var; daha uzun metnin sonu `… devamı Gmail'de` oluyor.
Karakterler ve HTML varlıkları parça sınırında bölünmüyor. Takip mesajları mevcut
gönderim yordamını kullandığı için sessiz gönderim ve bir saniyelik gönderim
aralığı kartlarla aynı.

## Hatalar ve devam etme

| Senaryo | Davranış ve test kapsamı |
| --- | --- |
| Gmail gövdesi okunamıyor: bağlantı, izin veya 404 | Kart teslim edilip gönderildi olarak kaydediliyor. Hesap, gönderen ve kısaltılmış konuyu içeren tek uyarı ekleniyor: tam metin okunamadı. Uygulama düzeyinde tekrar döngüsü yok; diğer kartlar gönderiliyor ve Telegram teslimleri tamamlandığında tur kapanıyor. Sonraki tur aynı maili tekrar okumuyor. |
| `fetch_body` boş metin döndürüyor | Takip mesajı ve uyarı gönderilmiyor; kart gönderilmiş kalıyor, tur tamamlanıyor. |
| Tam metnin bir parçası mesaja özgü kalıcı Telegram 400 hatası alıyor | O mailin kalan parçaları bırakılıyor, maili tanıtan tek uyarı ekleniyor ve sonraki karta geçiliyor. Kart gönderilmiş kalıyor; sonraki turlarda kart ve metin yeniden gönderilmiyor. İlk veya ikinci parçanın reddi test edildi. |
| Tam metin gönderimi geçici hata veya izin/sohbet hatası alıyor | Mevcut erteleme akışı çalışıyor; tur açık kalıyor. 429 için `retry_after`, izin/sohbet hataları için mevcut bir saatlik bekleme korunuyor. Kart önceden gönderildi olarak kaydedildiği için devam ederken tekrar gönderilmiyor. **Tercih: o mailin kalan tam metin parçaları yeniden denenmiyor; sahibine maili tanıtan bir uyarı ile Gmail'den kontrol etmesi söyleniyor.** Ulaşmış olabilecek parçalar da tekrarlanmıyor. Sonraki kartlar ve bekleyen uyarılar devam ediyor. |
| Uyarının teslimi de geçici hata alıyor | Uyarı kalıcı bekleyen uyarı kaydında tutuluyor ve devam ederken gönderiliyor. Kart, tam metin ve Gmail işlemi tekrarlanmıyor. |
| Uyarı mesajı kalıcı olarak reddediliyor | Mevcut kısa uyarı yedeği kullanılıyor. Loga yalnız maili tanıtan uyarı bilgisi giriyor; gövde ve hata içindeki URL/token bilgisi girmiyor. |
| Çok uzun gövde; `<`, `&`, emoji ve diğer astral karakterler | 100.000 karakterlik düz metin ve 120.000 karakterlik özel karakter gövdesi test edildi. Tüm parçalar kaçırıldıktan sonra sınırın altında, en fazla dört mesaj. Sınırın altında kalan bölünmüş gövdelerde metnin kayıpsız ve tekrarsız birleştiği ayrıca doğrulandı. |
| HTML-only, multipart/alternative, iç içe multipart ve ek | HTML dönüşümü, düz metnin parça sırasından bağımsız tercihi, iç içe gezinme ve ek alt ağaçlarının atlanması doğrulandı. |
| Eksik veya yanlış charset | Eksik/tanınmayan charset UTF-8'e düşüyor; bildirilen charset ile çözülemeyen baytlar yerine değiştirme karakteri geliyor. UTF-8, ASCII ve ISO-8859-9 örnekleri test edildi. |
| Kişisel veri | Gövde yalnız bellekte tutuluyor; loga, SQLite tablolarına veya meta kayıtlarına yazılmıyor. Başarılı teslim, kalıcı/geçici hata ve uyarı yedeği yollarında özel gövde işaretinin log ve veritabanı dökümünde bulunmadığı test edildi. Hata açıklamaları uyarılara veya loglara kopyalanmıyor. |

Geçici hata testleri bağlantı hatası, 503, 401, 403, sohbet düzeyinde 400 ve 429'u;
ilk/ikinci parça hatasını ve mesaj ulaştıktan sonra hata dönmesi ihtimalini kapsıyor.
Gmail işlemi yalnız bir kez uygulanıyor. Gönderilmiş kartın Telegram mesaj kimliği
korunuyor. Özet, kartlar ve sondaki uyarıların mevcut sırası korunuyor; tam metin
ilgili kartın hemen ardından araya giriyor. Kısa kart yedeği başarıyla teslim
edilirse tam metin geliyor; kartın iki sürümü de reddedilirse gövde okunmuyor.

Tam metin okuması Gmail etiketlerini ve okunma durumunu değiştirmiyor. Silme
çağrısı eklenmedi, gizli bilgi saklama düzeni değiştirilmedi. Veritabanı şeması ve
mevcut dış arayüzler korundu.

## Değişen dosyalar

- `mail_ajani/gmail.py`: salt okunur gövde çekme ve MIME/HTML çözümleme.
- `mail_ajani/render.py`: kaçırılmış UTF-16 hesabı ve sınırlı tam metin parçaları.
- `mail_ajani/tur.py`: otomatik önemli kartın ardından gönderim, hata ve erteleme akışı.
- `tests/helpers.py`: sahte Gmail istemcisinde gövde, hata ve çağrı takibi.
- `tests/test_gmail.py`: MIME, charset, boş içerik, hata ve salt okunur istek testleri.
- `tests/test_render.py`: kaçırma, uzunluk, parça sınırı ve kayıpsız bölme testleri.
- `tests/test_tur.py`: kapsam, sıra, sessizlik, gönderim aralığı, gizlilik ve devam etme testleri.
- `docs/ozellik-tam-metin.md`: bu rapor.

`mail_ajani/telegram.py` ve mevcut Telegram testleri okundu; Telegram istemcisinde
değişiklik gerekmedi. Mevcut testlerin hiçbir doğrulaması zayıflatılmadı.

## Doğrulama

Kullanılan komut:

```sh
MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q
```

Son çıktı:

```text
........................................................................ [ 26%]
........................................................................ [ 53%]
........................................................................ [ 80%]
......................................................                   [100%]
270 passed in 0.68s
```

Mevcut 209 teste 61 yeni test örneği eklendi; tamamı geçti.

```text
$ plutil -lint launchd/*.plist
launchd/com.oguzhan.mail-ajani.dinleyici.plist: OK
launchd/com.oguzhan.mail-ajani.tur.plist: OK
```

Kontroller izole geçici uygulama/veri ve log dizinleriyle, sahte Gmail/Telegram
istemcileriyle yapıldı. Google veya Telegram'a bağlanılmadı; paket kurulmadı,
git/claude/Agent çağrısı yapılmadı. Launchd süreçleri yüklenmedi veya yeniden
başlatılmadı. Canlı teslim testi yapılmadı.

Sahibinin karar vermesi gereken açık konu yok. Dört mesaj sınırı ve geçici hatadan
sonra kalan gövde parçalarını uyarıyla bırakma tercihi, istenen tasarım içinde
uygulandı.
