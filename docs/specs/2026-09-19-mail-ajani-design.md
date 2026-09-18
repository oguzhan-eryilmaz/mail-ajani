# Mail Ajanı: Tasarım

Tarih: 19 Eylül 2026 · Durum: Oğuzhan onayı bekliyor

## Amaç

Oğuzhan'ın üç Gmail hesabına (iki Google Workspace, bir kişisel) gelen mailleri tek yerde
toplamak, önemliyi kaçırmamak ve kalabalığı ayıklamak. Ajan başta hiçbir kararı kendi
vermez; Oğuzhan'ın Telegram'daki düğme seçimlerinden öğrenir ve güven kazandıkça kendi
karar vermeye geçer.

Kapsam dışı (ilk sürüm): cevap taslağı yazmak, Obsidian'a özet düşmek, mail göndermek.

## Kısıtlar

- **Ek maliyet yok.** Sunucu kiralanmaz; her şey Oğuzhan'ın sürekli açık Mac'inde çalışır.
  Yapay zekâ kararı mevcut Claude Max aboneliği üzerinden Claude Code'un başsız modu
  (`claude -p`, model Sonnet) ile alınır. Gmail API ve Telegram Bot API ücretsizdir.
- Kod `~/Developer/mail-ajani`, GitHub'da **private** repo olarak paylaşılır.
- Gizli bilgiler (Gmail OAuth jetonları, Telegram bot anahtarı) macOS Anahtar Zinciri'nde
  durur; repoya, vault'a ve loglara yazılmaz.
- Öğrenme verisi (gönderenler, örnek kararlar, kurallar) kişisel veridir; repoya girmez,
  `~/Library/Application Support/mail-ajani/` altında yerel veritabanında durur.

## Bileşenler

İki süreç, ortak bir yerel veritabanı (SQLite).

### 1. Tur (zamanlanmış, günde 4 kez)

- Saatler: 00:00, 06:00, 12:00, 18:00 (İstanbul). macOS `launchd` ile tetiklenir.
- Mac o saatte uykudaysa/kapalıysa açılışta kaçırılan tur çalışır; aralık "son başarılı
  turdan bu yana" olarak hesaplanır, arada mail düşmez.
- Akış:
  1. Üç hesaptan, son turdan beri gelen yeni mailleri çek (Gmail API, geçmiş kimliğiyle).
  2. Daha önce Telegram'a gönderilmiş mailleri ele (bir mail asla ikinci kez gönderilmez).
  3. Kesin kuralları uygula (yapay zekâ çağrısı yok).
  4. Kalanları **tek toplu çağrıda** Sonnet'e gönder: gönderen, konu, kısa gövde özeti,
     Gmail sekmesi (Tanıtımlar/Sosyal/Güncellemeler) + Oğuzhan'ın son örnek kararları.
     Sonnet her mail için `cop | arsiv | onemli | kalsin | emin_degil` ve 1-2 satır Türkçe
     özet döndürür.
  5. Otonom yetkisi olan türlerde kararı uygula; diğerlerini Telegram'a kart olarak gönder.
  6. Yeni mail yoksa **hiç mesaj gönderme.**
- Gece turu (00:00, 06:00) bildirimleri sessiz gönderilir.

### 2. Dinleyici (sürekli açık, yapay zekâsız)

- Telegram Bot API'yi dinler (long polling; Mac'e Telegram uygulaması kurulmaz, Oğuzhan
  düğmelere telefondan basar).
- Düğmeye basıldığında işlemi anında Gmail'e uygular, kartı "✓ Çöpe atıldı" gibi günceller,
  kararı örnek olarak kaydeder.
- Komutlar: `/kurallar` (öğrenilenleri listeler, silme düğmesiyle), `/durum` (son tur,
  hata var mı).
- `launchd` ile açılışta başlar, çökerse yeniden başlar.

## Telegram mesajları

- Tur başına önce özet: "12:00 turu · 14 yeni · 3 önemli · 5 senin kararını bekliyor".
  Ajan bir şeyi kendi yaptıysa özet onları listeler, yanlarında **Geri al** düğmesi olur.
- Her mail için kart: hesap, gönderen, konu, 1-2 satır özet, ajanın tahmini.
  Düğmeler: 🗑 Çöp · 📦 Arşiv · ⭐ Önemli · ✓ Kalsın.
- Önemli tahminli kartlar başta, gerisi sonra.
- Telegram'a gönderilen mail Gmail'de okunmadı olarak kalır; "görüldü" yalnız ajanın kaydıdır.
  Düğmeye basılmayan mail Gmail'de olduğu gibi kalır.

## İşlemlerin Gmail karşılığı

| Düğme | Gmail'de |
|---|---|
| 🗑 Çöp | Çöp kutusuna taşınır (30 gün geri alınabilir) |
| 📦 Arşiv | Gelen kutusundan çıkar, `Ajan/Arşiv` etiketi eklenir |
| ⭐ Önemli | Yıldız + `Ajan/Önemli` etiketi, gelen kutusunda kalır |
| ✓ Kalsın | Değişiklik yok, sadece örnek olarak kaydedilir |

## Öğrenme: kademeli güven

**Başlangıçta hiçbir şey otomatik değildir:** çöp, arşiv, önemli dahil her mail düğmeli
kart olarak gelir. Otomatik davranış yalnız aşağıdaki eşikler aşılınca, tür tür açılır.

1. **Kesin kural (gönderen bazlı):** Aynı gönderen adresine 10 kez üst üste aynı karar
   verilirse kural oluşur ve sonraki maillerde yapay zekâya sormadan uygulanır.
2. **Tarz yetkisi (tür bazlı):** Sonnet'in her tahmini Oğuzhan'ın gerçek kararıyla
   karşılaştırılır. Bir karar türünde (çöp, arşiv, önemli ayrı ayrı) son 30 tahminin en az
   %95'i tutmuşsa Sonnet o türde kendi karar verir.
3. **Geri al = güven sıfırlanır:** Otomatik bir kararı geri almak, o kuralı siler ya da o
   türün yetkisini kapatır. Sayaç yeniden başlar.
4. **Görünür hafıza:** `/kurallar` tüm kuralları ve tür yetkilerini okunur listeler;
   Oğuzhan istediğini silebilir.

"Önemli" otomatik kararında ajan yalnız işaretler ve Telegram'a gönderir, maili gizlemez.

## Güvenlik bariyerleri

- Daha önce ⭐ verilmiş bir gönderen asla otomatik çöpe ya da arşive gitmez.
- Kalıcı silme yok; en sert işlem Gmail çöpü.
- Sonnet çağrısı başarısız olursa (limit dolu, hata, bozuk cevap) mailler tahminsiz,
  düğmeli gelir; hiçbir mail işlemsiz kaybolmaz.
- Gmail izni düşerse ya da bir hesap okunamazsa Telegram'a uyarı gider, diğer hesaplar
  çalışmaya devam eder.
- Dinleyici yalnız Oğuzhan'ın Telegram sohbet kimliğinden gelen düğme ve komutları kabul eder.

## Kurulumda Oğuzhan'ın yapacakları

1. Telegram'da BotFather ile bot açmak (anahtar doğrudan Anahtar Zinciri'ne girilir).
2. Google Cloud'da ücretsiz bir proje ve OAuth izni; üç hesap için birer kez "izin ver".
   Workspace hesaplarında yönetici izni gerekebilir.
3. Mac'in uyku ayarı: sistem uyumasın (ekran kapanabilir).

## Test

- Gmail ve Telegram ile konuşan katmanlar sahte (mock) sürümlerle test edilir; kural
  motoru, güven eşikleri, tekrar gönderme engeli ve kaçırılan tur hesabı birim testlerle
  doğrulanır.
- Canlı deneme: tek hesapla bir tur, gerçek Telegram mesajı, düğmenin Gmail'e yansıması.
