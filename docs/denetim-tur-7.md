# Mail Ajanı: bağımsız denetim, tur 7 (E6-1, Ö6-1, Ö6-3, Ö6-4 doğrulaması)

Tarih: 5 Ekim 2026 · Denetleyen: Opus (salt okunur) · Konu: `c0f923f` (HEAD). İstek gereği yalnız engel düzeyindeki ve gözetimsiz çalışmadan
önce düzeltilmesi gerekenler yazıldı. Canlı veritabanı ve ayar dosyası açılmadı; her deneme geçici `MAIL_AJANI_HOME`/`MAIL_AJANI_LOGS` ile
yapıldı.

## Karar

**Evet: kategoriler canlı mail için açılabilir, ama `kategori-kur`'un yazdığı geçerli ayarla ve `config.json` elle düzenlenmeden.**

E6-1, Ö6-3 ve Ö6-4 kapandı. Ö6-1 **kısmen** kapandı: teslimat artık durmuyor ve ayar dosyası atomik yazılıyor. Ancak ayar geçersizse kod
"kategoriler kapalı" davranışına dönüyor ve gönderen kuralı, kategorisi değerlendirilmemiş bir faturayı çöpe atıyor (**E7-1**). Bu, ayarın
geçerli olduğu sürece tetiklenmez. Gözetimsiz çalışmadan önce düzeltilmeli.

## Çalıştırılan kontroller ve sonuçları

| Kontrol | Sonuç |
|---|---|
| `MAIL_AJANI_HOME=$(mktemp -d) MAIL_AJANI_LOGS=$(mktemp -d) .venv/bin/pytest -q` | geçti (392 passed) |
| E6-1: Diğer ekleniyor mu, şema, kural/tarz Diğer'e uygulanıyor mu, bozuk cevapta bariyer ve tek uyarı | geçti |
| Ö6-1: geçersiz ayar (`"onemli": "true"`), üç çağrı, kural kapsamında fatura maili | teslimat ve uyarı doğru; **E7-1** |
| Ö6-3: gerçek `GmailClient`, sahte servis: küçük harfli ve NFD etiket, 409 → yeniden liste, `Ajan/Arşiv` | geçti |
| Ö6-4: `attachmentId` gövde, ek okunamazsa, yalnız PDF ekli mail, turda okunamayan gövde uyarısı, logda gövde | geçti |
| Tur 6 senaryoları S1-S6 ve tur 1-5 yeniden üretimleri | gerileme yok |
| Çalışan eski dinleyici (hâlâ 02:17:42'de başlayan süreç, kod `493804a`) ile S4 göç ve S5 uyumluluk | geçti |
| `git show HEAD -- tests`: değişen iddialar | meşru (aşağıda) |
| Gerçek Gmail, Telegram, `claude`, launchd, canlı ayar ve veritabanı | çalıştırılmadı / açılmadı |

## Bulguların durumu

### E6-1: **kapandı**

- **Diğer ekleniyor:** `get_categories` listede "Diğer" yoksa ekliyor, ayar dosyasına yazmıyor:
  `['Bülten', 'Diğer'] | ayar dosyası değişmedi: True`. Diğer her zaman önemsiz.
- **Şema, kategoriler açıkken:** `enum: [..., 'Bülten', 'Diğer']`, `required: ['id', 'karar', 'ozet', 'kategori']`.
- **Şema, kategoriler kapalıyken:** `required: ['id', 'karar', 'ozet']`, enum yok. Prompt tur 6'da `c79c047` ile birebir aynıydı; bu commit
  yalnız kategorili satırı değiştirdi.
- **Diğer'e kural ve tarz normal uygulanıyor, uyarı yok:**
  `gmail: [('g901', 'cop'), ('g902', 'arsiv')] | etiket: [… 3 × 'Diğer'] | uyarı: 0 | kart: 1`.
- **Gerçekten eksik, bozuk ya da uydurma cevapta bariyer duruyor:** Kural ve tarz kapsamındaki 3 mail için (sonuç yok, boş, `Spam`):
  `gmail: []`, tek uyarı satırı: "Bazı mailler için geçerli kategori alınamadı; bu maillerde otomatik işlem yapılmadı." Sınıflandırıcı
  çökünce de aynı (`gmail: []`, 1 uyarı). Tur 6'nın S1 beş durumunda da `gmail=[]`, uyarı 1.
- **Kör çöp/arşiv yeniden arandı:** Kategoriler geçerliyken bulunamadı. Tur 6'daki S1f (önceki turda değerlendirilmiş önemsiz kategori + sonradan
  oluşan kural) kör sayılmaz. Tek yol E7-1.

### Ö6-1: **kısmen**

- **Teslimat sürüyor, dilim başına tek uyarı:**
  `12:00 {'new': 2, …}`, `12:15 {'skipped': True}`, `18:00 {'new': 1, …}`, `uyarı mesajları: 2` (iki dilim, ikişer değil birer).
- **Ayar atomik yazılıyor:** geçici dosya + `fsync` + `os.replace`; artık geçici dosya kalmadı. Dinleyici `/kurallar` geçersiz ayarda hata
  yerine uyarı satırı gösteriyor.
- **Eksik kalan:** E7-1.

### Ö6-3: **kapandı**

Ad karşılaştırması NFC + `casefold`:

- `küçük harf -> kullanılan: {'addLabelIds': ['LV']} create: 0`, NFD için aynı.
- 409 → liste yeniden çekiliyor: `{'addLabelIds': ['L409']}`.
- Listede hâlâ yoksa `HttpError 409` → mevcut etiket hatası yolu (uyarı, önemsiz kategoride otomatik işlem yok).
- `Ajan/Arşiv` hâlâ bulunuyor.

### Ö6-4: **kapandı**

- **Ek kimlikli gövde:** `attachments.get(userId='me', messageId, id)` ile okunuyor: `'GIZLIGOVDE uzun bülten'`.
- **Ek okunamazsa:** `BodyUnreadableError`; turda tek uyarı geliyor: "Mail #1 (a · s@x.com · Yeni giriş): tam metin okunamadı; Gmail'den
  kontrol edin.". Dilim kapanıyor, 12:15'te gövde yeniden okunmuyor.
- **Yalnız PDF ekli mail:** hata değil, boş metin; takip mesajı gitmiyor.
- **Gizlilik:** Gövde logda yok (`logda gövde: False`). Veritabanı dökümünde de yok (S3 tekrarı: `gövde DB'de: False | logda: False`).

### Değişen test iddiaları: **meşru**

- **Gövde testleri:** "boş döner" testindeki dört örnek (görüntü, boş metin, ek kimlikli, yalnız script/style) yeni
  `test_fetch_body_signals_present_but_unreadable_body` testine taşındı. Bu test `BodyUnreadableError` bekliyor ve ayrıca `modify`, `trash`,
  `delete` ve etiket çağrısı yapılmadığını doğruluyor; iddia daha sıkı.
- **Uyarı sayısı:** `stats["warnings"] >= 1` → `== 1`, daha sıkı.
- **Şema:** "`kategori` zorunlu değil" → "zorunlu ve `enum` tanımlı adlar"; yeni sözleşme.
- **Varsayılan liste:** sonuna `Diğer` eklendi; önemli kategoriler aynı.
- Başka silinen ya da gevşetilen iddia yok.

## Gerileme

Tur 6 S1-S6 sonuçları aynı:

- güvenlik bariyeri;
- önemli kategorinin kuralı yenmesi;
- öğrenme yalıtımı;
- tam metin devamı;
- `kategorile`'nin yan etkisizliği, 404 ve kilit.

Tur 1-5 yeniden üretimleri de aynı: R1-R5, R9, N1-N5, Ö-A, 35 ret, uyarı reddi.

Çalışan eski dinleyicinin koduyla:

- kategori kararını geri alma doğru (`revert onemli`, `undone 1`, kural duruyor);
- kategori kartında Arşiv doğru;
- eski şemadan göç, eski bağlantı açıkken veri kaybetmeden ve bir kez yapılıyor.

## Gözetimsiz çalışmadan önce düzeltilmeli

### E7-1. Kategori ayarı geçersizse gönderen kuralı, kategorisi değerlendirilmemiş maili (fatura dahil) çöpe atıyor

- **Yer:** `mail_ajani/tur.py:59-66` (geçersiz ayarda `categories = {}`), ardından `tur.py:68-71` kural kapsamındaki maili sınıflandırıcıya
  göndermiyor. Karar döngüsü de kategori yokmuş gibi `learning.auto_action`'a gidiyor.
- **Tetikleyici:** `config.json`'daki `kategoriler` listesinin elle bozulması; örneğin `"onemli": "true"`, tekrar eden ad ya da metin olmayan
  `renk`. `kategori-kur` geçerli ayar yazdığı için ancak elle düzenlemede olur.
- **Etki:** Sahibin "fatura, güvenlik ve işbirliği maili, gönderen kuralı çöpe atacak olsa bile önemli" şartı bu durumda çiğneniyor. Çöp ve
  arşiv kuralları ile tarz yetkileri kategori değerlendirmesi olmadan uygulanıyor. Telegram'a "Kategori ayarı geçersiz; bu tur
  kategorilendirme kapalı" uyarısı gidiyor ve mail 30 gün çöpten geri alınabiliyor; ama kural kapsamındaki önemli mail kart olarak gelmiyor.
- **Kanıt (çalıştırıldı):** Geçersiz ayar, `fatura@sirket.com` için çöp kuralı, konu "Ekim faturanız":
  ```
  12:00 {'new': 2, 'auto': 1, 'cards': 1, 'warnings': 1}
  gmail: [('g901', 'cop')] | sınıflandırıcıya giden konular: ['Konu', 'Konu']
  ```
  Fatura maili sınıflandırıcıya hiç gitmeden çöpe atıldı.
- **Düzeltme:** Geçersiz ayarda kategorileri "açık ama değerlendirilemedi" say. Bu turda hiçbir mail için kural ya da tarz kaynaklı çöp/arşiv
  uygulanmasın (`automatic = None`), mailler kart olarak gelsin, mevcut tek uyarı kalsın. Kısa vadede: düzeltilene kadar `config.json` elle
  düzenlenmemeli.

## Dağıtım notu

Tur 6'daki sıra geçerli. Dinleyici hâlâ eski süreç (02:17:42). Eski kod uyumlu, ama kategoriler açılmadan önce yeniden başlatılmalı:

1. `launchctl kickstart -k gui/$(id -u)/com.oguzhan.mail-ajani.dinleyici`
2. `kategori-kur`. Ayar artık atomik yazıldığı için zamanlama kısıtı yok.
3. `kategorile`, bir dilim tamamlanmışken.

Açık soru tur 6'dakiyle aynı: `Kategori/<ad>`'ın Gmail'de iç içe görünümü ve gerçek `claude -p`'nin zorunlu `enum` şemasına uyduğu, canlıda
ilk turda bakılmalı.
