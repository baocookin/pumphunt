# Bot "rây": năm luật, đánh giá red team, và bản v1 (08/10/2026)

Tài liệu này gồm bốn phần:
- năm luật thiết kế ban đầu cho một bot tín hiệu pump.fun theo kiểu "loại đá, không tìm vàng";
- kết quả kiểm các luật đó trên dữ liệu của dự án;
- đánh giá của một agent red team;
- đặc tả một bản v1 đo được.

Nguồn: 4 agent nghiên cứu (bẫy, đám đông nhận tín hiệu, tính khả thi, dữ liệu) và 1 agent red team. Workflow `wf_1219f63c-46d`, 07–08/10/2026. Số liệu tự đo chỉ là **thăm dò**, chưa phải kiểm định.

Ký hiệu nguồn:
- **[OC]**: tự đo trên dữ liệu của dự án;
- **[S]**: chỉ thấy qua đoạn trích của kết quả tìm kiếm;
- **[V]**: số liệu của vendor, chưa kiểm chứng.

## Tóm tắt

1. Năm luật đúng về tinh thần: nghi ngờ mặt tiền, hỏi ai là người thua, đòi đo mọi thứ. Nhưng ba trong năm luật đang đo sai thứ cần đo (luật 1, 2 và 5).
2. **Chưa có tổ hợp lọc nào, cố định trước khi xem kết quả, để lại tập coin "được nhắn" có trung bình dương.** Điều này đúng ở mọi cách đã thử: quyết định ở phút 2, 5, 10 hay lúc 10–60 giây, và sau migration; bán sau 10 phút, 30 phút, hay giữ tới cuối.
3. Các bộ lọc **bắt bẫy tốt nhưng không tạo ra tín hiệu mua**:
   - loại hết bẫy thì phần còn lại là "bụi" ăn phí;
   - bộ lọc mạnh nhất loại luôn phần lớn số coin thắng.
4. Bản v1 trung thực là **bot cảnh báo** ("đừng mua X vì Y") cho riêng chủ bot, cộng một **sổ bóng** chạy thử đúng một luật mua đăng ký trước trong 14 ngày.
5. Nhiều khả năng luật mua đó bị KILL. Khi đó kết luận đúng là: trên pump.fun hiện tại, người ngoài chưa có tín hiệu mua dương EV ở tốc độ con người.

## 1. Năm luật ban đầu

> **I. Tư duy chiến trường — năm luật của kẻ sống sót**
>
> **Luật 1 — bất đối xứng:** bỏ sót một token tốt giá bằng 0. nuốt một token bẫy giá bằng cả position. bot này không tìm vàng — nó loại đá. bias được tune cho precision, không recall: thà im lặng cả ngày còn hơn hú một tiếng sai.
>
> **Luật 2 — mỗi tín hiệu là một câu hỏi:** "ai bán cho tao, và tại sao họ ngu hơn tao?" nếu không trả lời được, không có tín hiệu — chỉ có tiếng ồn được trang điểm. 86 nghìn ví mất 675K SOL vì trả lời "không ai cả, giá đang lên mà".
>
> **Luật 3 — tin dòng tiền, không tin mặt tiền:** chart có thể được vẽ (5 phút bán bám mua bucket-út-bucket của crew). PnL có thể được giả (SPL-transfer vào ví trắng). thứ không giả được: funding graph, supply concentration, và thời điểm tương đối của mọi lệnh.
>
> **Luật 4 — tốc độ của rây, không phải của súng:** bot này không đua slot nào. nó cần đúng tín hiệu trong 2-10 phút đầu — trước alert-crowd 30-120 giây là đủ, không cần mili-giây. đó là lý do nó chạy được trên $49 mày đã trả.
>
> **Luật 5 — mọi lọc phải đo được:** mỗi filter ghi số bẫy nó bắt được mỗi ngày. filter không bắt gì trong 7 ngày = dead weight, cắt. bot tự phẫu thuật chính nó.

## 2. Kiểm trên dữ liệu của dự án [OC]

### Thiết lập

**Dữ liệu**
- **Census:** mọi giao dịch trên bonding curve trong 2 giờ đầu của mẫu băm 5% số launch.
  - 1.498 launch classic (không mayhem), từ 06/10 20:53Z đến 07/10 20:27Z; 39 cái tốt nghiệp.
  - Không có cửa sổ bị cắt, không có đứt chuỗi.
- **loopholetape:** 72.563 launch classic, 27–29/9. Trạng thái và đặc trưng được chụp ở giây 10–60 (trung vị 10,6 giây), nên tập này kiểm quyết định rất sớm, không phải phút 2–10.
- **Migration:** 307 pool kiểu C2 (≥ 10 SOL thật lúc T+30, có swap trong 60 giây trước đó), có đặc trưng funding.

**Thời điểm quyết định:** D = 2, 5, 10 phút sau lệnh tạo. Chỉ xét launch chưa hoàn tất và có giao dịch trong 60 giây trước D. Số launch đạt điều kiện: 503 / 207 / 91.

**Vé và lối thoát**
- Vé 0,5 SOL, mua ở trạng thái curve cuối slot D+1. Phí 1,25% mỗi chiều, cộng 0,002 SOL.
- Ba lối thoát: (a) bán sau 10 phút; (b) bán sau 30 phút; (c) giữ tới tốt nghiệp hoặc hết cửa sổ 2 giờ.

**Định nghĩa "bẫy"** (ghi trước khi tính kết quả): lỗ ≥ 50% ở lối thoát (b).
- Hệ quả cơ học tìm ra sau đó: giá curve tỉ lệ với (30+x)². Vì vậy chỉ có thể lỗ 50% khi vào từ khoảng 12,4 SOL thật trở lên.
- Mọi bẫy đều là "curve cao rồi rơi", nên mức curve là biến gây nhiễu cho mọi bộ lọc.

**Bộ lọc:** ngưỡng của các cờ F1–F14 và các tổ hợp A–E được cố định trước khi xem kết quả:
- A = lõi luật 3: F1, F2, F3, F4, F7, F8, F9, F14;
- B = A cộng dòng tiền;
- C = tất cả 14 cờ;
- D = nhóm đối chứng momentum (≥ 5 SOL và đang tăng);
- E = D cộng A.

### Tỷ lệ nền

| Thời điểm | n | Tỷ lệ bẫy | Trung bình (a) 10 phút | (b) 30 phút | (c) giữ |
|---|---|---|---|---|---|
| D = 2 phút | 503 | 7,6% | −6,3% [−9,7; −2,8] | −9,9% [−12,8; −6,8] | −10,5% |
| D = 5 phút | 207 | 12,1% | −5,0% | −10,3% | −9,0% |
| D = 10 phút | 91 | 13,2% | −10,0% | −16,7% | −16,3% |

Các tập này chủ yếu là bụi. Trung vị curve chỉ 0,5–1,7 SOL thật, và dev đã bán ở 65–73% số launch.

Theo mức curve lúc D = 2 phút (lối thoát b):

| Mức curve (SOL thật) | n | Trung bình | Tỷ lệ bẫy |
|---|---|---|---|
| < 1 | 281 | −3,7% | 0% (chỉ mất phí, chắc chắn) |
| 1–5 | 125 | −15,2% | 0% |
| 5–13 | 41 | −30,6% | 2% |
| 13–30 | 40 | −27,9% | 75% |
| 30–86 | 16 | +22,0% | 44% (7 cái tốt nghiệp: chính là G/GS) |

Tầng "có lực" (≥ 5 SOL): tỷ lệ bẫy 39–45%, trung bình −21% đến −37%.

### Từng cờ (D = 2 phút, lối thoát b)

| Cờ | Định nghĩa (tóm tắt) | n cờ | Tỷ lệ bẫy: có cờ / không cờ | Ghi chú |
|---|---|---|---|---|
| F1 dev giữ | dev còn giữ nhiều cung | 59 | 19% / 6% | Trong tầng có lực vẫn còn tác dụng (48% / 36%). Một trong những cờ thật nhất |
| F2 top-1 | ví lớn nhất giữ nhiều | 102 | 12% / 7% | Chủ yếu phản ánh mức curve. Loại mất 4/7 coin thắng |
| F3 top-10 ≥ 20% | 10 ví lớn nhất giữ ≥ 20% cung | 77 | 44% / 1% | Lift 47 lần phần lớn là cơ học. Trong tầng có lực: loại 34/38 bẫy và đồng thời 6/7 coin thắng lớn |
| F4 insider | dev, creator, ví mua ở slot tạo và slot kế | 66 | 23% / 5% | Trong tầng có lực không có tác dụng. Insider là nơi sinh ra cả bẫy lẫn coin thắng |
| F5 / F10 curve mỏng hoặc thấp | | 261 / 406 | 0% / 16–39% | Không bắt bẫy nào (do cách định nghĩa) nhưng loại đúng nhóm chắc chắn lỗ phí. **Luật 5 sẽ cắt nhầm chính các cờ này** |
| F7 crew bán bám mua | bán đi theo mua, đã kiểm soát mật độ lệnh | 16 | 6% / 8% | Hiếm và không có tác dụng ở 2 phút. Có tác dụng ở 5 phút (30% / 11%, n=10), không xuất hiện ở 10 phút. Nếu không kiểm soát mật độ thì trông giống mọi bot bình thường |
| F8 wash | một ví mua rồi bán lại cùng lượng token trong vòng 2 slot, ≥ 3 vòng | 14 | 29% / 7% | Ổn định qua cả ba thời điểm. Trong tầng có lực: 4/4 cờ là bẫy và không loại coin thắng nào. **Cờ sạch nhất, nhưng n nhỏ** |
| F9 dev đã bán | | 327 | 6% / 10% | Bật ở 65% số coin, không có tác dụng. Chính cờ này làm các tổ hợp A, B, C, E rỗng |
| F12 spike | curve tăng ≥ 10 SOL trong 60 giây | 10 | 70% / 6% | Đuổi theo cú bơm vừa xảy ra: 70–75% là bẫy |
| F13 lướt nhanh | nhiều ví bán ngay sau khi mua | 74 | 22% / 5% | Có tác dụng vừa phải trong tầng có lực |
| X ví bán mà không mua (thăm dò) | ví bán nhiều hơn số đã mua trên curve, tức nhận token qua transfer | 160 | 16% / 3% | Dấu hiệu "chuyển SPL vào ví trắng" của luật 3. Có ở 57% coin trong tầng có lực, lift khoảng 1,6 |
| Funding (migration, T+30) | ví mới, cụm cùng nguồn tiền, liên kết dev | 32–47 | 38–51% / 42–44% | **Gần như không có tác dụng** sau 1 giờ. Ví mới chỉ nổi bật sau 24 giờ (100% / 80%, n=32) |

### Câu hỏi then chốt: phần còn lại sau khi lọc có lời không?

| Thời điểm, lối thoát | Tổ hợp | n | Trung bình | KTC 95% | Thắng |
|---|---|---|---|---|---|
| 2 phút, b | A lõi luật 3 | 89 | −4,7% | [−5,4; −4,1] | 0% (toàn bụi, 0 bẫy) |
| 2 phút, b | B, C, E | 0–2 | — | — | thực sự "im lặng cả ngày" |
| 2 phút, b | D momentum | 57 | −13,3% | [−35; +12] | 19% |
| 5 phút, b | A | 25 | +3,9% | [−6; +22] | 8% |
| 5 phút, b | D momentum | 29 | −27,9% | [−51; −1] | 17% |
| 10 phút, b | A | 8 | −9,7% | | 0% |
| loopholetape 10–60 giây, giữ | lõi luật 3, tầng có lực | 548 | −16,5% | [−27,5; −4,1] | 4% |
| Migration T+30, 1 giờ | các cờ funding | 238 | −33,2% | [−41; −24] | 29% |

Ba luật chọn sau khi đã xem dữ liệu, ở phút 5, trông dương. Ví dụ: có lực, top-10 < 20%, dev giữ < 3% cho n=13, trung bình +29%, KTC [−9; +73].
- Kết quả này dựa trên 3–4 vé tốt nghiệp.
- Cùng luật đó ở phút 2 và phút 10 lại âm.
- Vì vậy khả năng cao đây là nhiễu.

Đã xem khoảng 200 ô mà không hiệu chỉnh cho kiểm định bội. Với ngưỡng đặt trước (KTC loại 0, cả hai nửa thời gian dương), không phần còn lại nào đạt.

### Luật 4 trên dữ liệu

- Ghép cặp trên cùng các token momentum: vào trễ 30–120 giây sau khi tín hiệu xuất hiện làm trung bình thay đổi khoảng 0 (−0,05 đến +0,08, mọi KTC đều chứa 0).
- Lý do không tốt: lúc tín hiệu xuất hiện, cú tăng giá đã nằm trong giá. SOL mua vào giảm từ 3.468 trong 120 giây trước quyết định xuống 1.645 trong 120 giây sau.
- Vào sớm hơn tín hiệu 60 giây thì lời thêm 15–22 điểm, nhưng đó là nhìn trước tương lai, không ai bắt được.
- 79% số lần tốt nghiệp xong trong 60 giây đầu, 87% trong 120 giây, trung vị chỉ 4 ví mua. Phần lớn "coin thắng" trên curve đã xong trước khi cửa sổ 2–10 phút mở ra.

## 3. Đánh giá từng luật (red team)

Không luật nào bị bỏ. Cả năm đều phải sửa.

### Luật 1: sửa

**Vấn đề**
- **Dùng ngược thuật ngữ.** Với bộ lọc loại bẫy, precision là tỷ lệ coin bị loại đúng là bẫy, còn recall là tỷ lệ bẫy bị bắt. "Thà im lặng cả ngày" thực chất đòi recall cao với bẫy, tức precision cao với tập được nhắn. Viết như hiện tại, bộ lọc chỉ loại khi chắc chắn và để lọt bẫy.
- **Ngay cả precision của tập được nhắn cũng là mục tiêu sai,** vì lời nằm ở số ít coin tăng mạnh. Ví dụ: tổ hợp A có 0 bẫy nhưng trung bình −4,7%. Lọc top-10 loại 34/38 bẫy và 6/7 coin thắng. Cờ lịch sử creator không giảm bẫy nhưng lại cải thiện trung bình 11–16 điểm.
- **"Nuốt bẫy = mất cả position" sai trên curve.** Giá không thể xuống dưới giá khởi điểm, nên lỗ tối đa là 1 − (30/(30+x))²: −26% ở 5 SOL, −44% ở 10 SOL, −75% ở 30 SOL. Còn lên tới tốt nghiệp thì được (115/(30+x))², tức 8,3 lần từ 10 SOL. Trên curve, bất đối xứng chạy ngược lại: bỏ sót coin thắng mới tốn tiền.
- Luật này **đúng sau migration:** pool kiểu C2 có trung bình −67,8% sau 24 giờ, 82% là bẫy.

> **Luật 1 (sửa) — bất đối xứng, tính bằng tiền:** không nhắn MUA khi chưa chứng minh được tập được nhắn có mean net > 0 sau phí, đo forward. Trên curve bẫy có trần lỗ (1−(30/(30+x))², 10 SOL → −44%), sau migration bẫy về 0 → không bao giờ ôm qua migration. Winner là thứ trả tiền cho mọi lệnh thua: mỗi filter phải khai nó giết bao nhiêu winner, không chỉ bắt bao nhiêu bẫy. Im lặng là output hợp lệ, nhưng mọi coin bị chặn vẫn ghi sổ bóng để đo.

### Luật 2: sửa

**Vấn đề**
- Trên bonding curve, bên kia giao dịch là chương trình, không phải người. Khoản lỗ đến từ những người bán *sau* mình.
- Trong 30 phút sau khi vào: 58–65% lượng SOL bán ra đến từ các ví mua sau thời điểm quyết định; insider chỉ 1–4%; top-10 lúc quyết định 13–16%. Tỷ lệ này như nhau ở bẫy lẫn không bẫy, nên danh tính người bán không phân biệt được bẫy.
- Ở phút 2–10, người bán là người vào sớm (khoảng 48%), bot lướt (khoảng 44%), dev và ví nhận transfer (khoảng 8%). Không nhóm nào "ngu hơn" một cách có hệ thống. KOL vào trong vài giây đầu, gần giá khởi điểm, rồi bán cho đám đông đến sau [V].
- Trả lời thật lòng thì câu hỏi có hai mặt: còn bao nhiêu hàng rẻ sắp đổ vào mình, và ai sẽ mua sau mình. Câu trả lời thường là "đám đông nhận tín hiệu đến sau". Nghĩa là lợi thế lấy từ khoản lỗ của người khác; nếu chia sẻ tín hiệu, chính người theo sẽ thành đám đông đó.
- Con số 86 nghìn ví / 675K SOL không tìm thấy nguồn (xem mục 6).

Điểm tốt: kỷ luật "ai là người thua" là ý hay nhất trong cả năm luật.

> **Luật 2 (sửa):** mỗi tín hiệu trả lời ba câu bằng số: (a) còn bao nhiêu hàng rẻ chưa bán có thể đổ vào tao (dev/bundle/ví nhận transfer: % supply và số SOL rút được khỏi curve); (b) ai mua sau tao với giá cao hơn, vì sao họ đến muộn, và độ trễ đó đo được chưa; (c) sau 2,5% phí khứ hồi cộng trượt giá, mean forward còn dương không. Không trả lời được (c) bằng dữ liệu forward thì không có tín hiệu. Bỏ con số 86k ví / 675K SOL cho tới khi có nguồn.

### Luật 3: sửa

**Vấn đề: "không giả được" là sai. Mọi thứ đều giả được, chỉ khác giá phải trả.**
- **Funding graph:** "che giấu địa chỉ creator" là một trong năm loại thao túng mà bài *Meme Coin Factories* (CCS'26) liệt kê. Nạp tiền qua sàn vừa tạo liên kết giả vừa che liên kết thật.
- **Độ tập trung cung:** chia ra 17–21 ví là qua mặt được.
- **Thời điểm lệnh:** có thể rải qua nhiều slot.
- **SOL ròng trong curve:** insider tự bơm được, chỉ tốn khoảng 2,5% phí khứ hồi.
- Trong tầng có lực, độ nâng (lift) thô của các cờ (top-10 47 lần, insider 14 lần, bundle 12 lần) co lại còn 1–3,5 lần, hoặc khoảng 1. Cờ funding không có tác dụng sau 1 giờ. Mẫu "crew bán bám mua" hiếm khi có thật khi đã kiểm soát mật độ lệnh.
- PumpPortal chỉ chuyển khoảng 29k trong khoảng 57k lệnh tạo mỗi ngày, và báo sai địa chỉ curve của coin mayhem. Thứ mình tưởng là "toàn bộ dòng tiền" có thể chỉ là một nửa.

Điểm tốt: volume, số holder, PnL, chart là những thứ rẻ nhất để giả (wash-trade chiếm ít nhất 17% giao dịch, theo CCS'26). Xếp hạng đúng hướng.

> **Luật 3 (sửa) — tin thứ đắt để giả, và biết giá của nó:** xếp mọi feature theo chi phí giả: volume/holder/PnL/chart gần như miễn phí; SOL ròng khóa trong curve tốn khoảng 2,5% phí; supply theo cụm ví buộc phải chia ví và chịu giá xấu hơn; funding graph buộc phải đi qua sàn hoặc ví già (loại funder có fan-out cao). Không feature nào "không giả được". Chỉ tin dòng tiền mình thấy đủ: luồng trade không khớp reserve của curve thì ghi "THIẾU DỮ LIỆU", không phải "sạch".

### Luật 4: sửa

**Vấn đề**
- Không có nghiên cứu nào đo lợi thế đi trước đám đông nhận tín hiệu.
- Phần lớn coin chạy về tốt nghiệp đã xong trước phút thứ 2.
- Vào trễ 30–120 giây không thay đổi trung bình, vì không còn đà tăng để mất.
- Ngân sách $49 chỉ đủ khi lọc theo tầng:
  - Kích hoạt kiểu ngây thơ ("chạm 10 SOL trong 10 phút") cần khoảng 1,2 triệu credit mỗi ngày.
  - Bộ ghi dữ liệu đã dùng khoảng 9 triệu trong 10 triệu mỗi tháng, chỉ còn khoảng 33k mỗi ngày.

Điểm tốt: bộ lọc loại bẫy đúng là không cần tốc độ tính bằng slot. Phút 2–10 cũng là lúc cú xả lộ ra, rất hợp để phủ quyết. Nút thắt thật là độ trễ của người (30–90 giây), và phải đưa nó vào mọi backtest.

> **Luật 4 (sửa) — tốc độ của người, không phải của bot:** mọi backtest vào lệnh ở T+45 s và T+90 s sau tín hiệu, ở giá curve thật, với ticket thật. Tín hiệu chỉ có giá trị nếu mean vẫn dương sau độ trễ đó. "Đi trước đám alert 30–120 s" là giả thuyết, phải đo được (ghi thời điểm call/trending) trước khi dùng. Ngân sách: lọc miễn phí từ stream trước, RPC trả phí chỉ cho tối đa 300 ứng viên còn sống mỗi ngày, trần 30k credit/ngày. Hết credit thì báo "THIẾU DỮ LIỆU", không im lặng.

### Luật 5: sửa

**Vấn đề: mục tiêu đúng, thước đo sai.**
1. Khi khoảng 98% coin là bẫy, đếm "số bẫy bắt được" không mang thông tin. Ở quy mô toàn bộ luồng dữ liệu, mọi cờ có ích bắt 20–700 bẫy mỗi ngày, nên quy tắc "7 ngày không bắt gì" không bao giờ kích hoạt với chúng.
2. Những cờ duy nhất bắt 0 bẫy là cờ curve mỏng hoặc thấp (do cách định nghĩa bẫy), và chúng loại đúng những coin chắc chắn lỗ phí. Luật 5 sẽ cắt nhầm chúng.
3. Bộ lọc chạy sau các bộ lọc khác thì bắt 0 vì vị trí của nó, không phải vì vô dụng.
4. Bộ lọc canh thảm hoạ hiếm trông như vô dụng cho tới khi pump.fun đổi luật chơi. BOOST đã đẻ ra self-graduation; Callout Rewards và Holder Rewards đang trợ giá cho volume và số holder giả. Bộ lọc đang răn đe đối thủ cũng trông như vô dụng.
5. Dữ liệu bị thiếu cũng sinh ra số 0.
6. Tự động "phẫu thuật" trên số đếm hằng ngày đầy nhiễu là đào bới dữ liệu. Mô hình cửa sổ sớm của Kamat có AUROC 0,859 trong mẫu nhưng chỉ 0,464 trên 14 ngày sau.
7. Đếm bẫy và tiền có thể mâu thuẫn: cờ lịch sử creator không giảm bẫy nhưng lại cải thiện trung bình 11–16 điểm.

> **Luật 5 (sửa) — mọi lọc phải đo được, tính bằng tiền:** mỗi filter chạy độc lập trên mọi ứng viên và ghi: số cờ, tỉ lệ bẫy cờ/không cờ trong cùng tầng mức curve, mean net cờ/không cờ, số winner nó giết, số credit tốn. Chỉ cắt filter tốn credit, và chỉ khi có từ 200 cờ forward trở lên mà khoảng tin cậy của chênh lệch mean chứa 0. Việc cắt do người duyệt, có version. Filter miễn phí không bao giờ bị cắt vì im lặng. Mỗi lần pump.fun đổi luật chơi thì bật lại toàn bộ và kiểm lại từ đầu.

## 4. Các luật còn thiếu

| Luật | Nội dung | Vì sao |
|---|---|---|
| **0 — định nghĩa sự thật** | "Bẫy" là lỗ ≥ 50% ở lối thoát đã định, tính ở giá khớp được, sau phí; "tốt" là lời > 0 sau phí. Luôn báo cáo theo tầng mức curve (< 5, 5–13, 13–30, 30–85 SOL). Định nghĩa, khoảng thời gian và lối thoát được ghi vào file đăng ký trước khi xem kết quả | Thiếu nhãn thì luật 1 và 5 không đo được, và tỷ lệ bẫy chỉ phản ánh mức curve |
| **6 — kỳ vọng lời là thước đo duy nhất của lệnh MUA** | Chỉ có tín hiệu MUA khi tập được nhắn, đo forward và đăng ký trước, có trung bình > 0 sau phí, trượt giá và độ trễ của người; cận dưới KTC > 0; cả hai nửa thời gian dương | Mọi tổ hợp đăng ký trước đều âm hoặc chưa chứng minh được. Bot "chính xác nhưng im lặng" có thể che một tập được nhắn đang lỗ |
| **7 — tín hiệu kèm lối thoát** | Thoát cố định: bán hết sau 30 phút, hoặc trong 60 giây sau migration nếu curve hoàn tất. Không bao giờ ôm qua migration. Đổi lối thoát là ra luật mới, phải kiểm lại | Kết quả đảo chiều theo lối thoát: tập momentum +1,7% nếu bán sau 10 phút, −13% nếu bán sau 30 phút. Mọi kiểu giữ qua migration đều âm |
| **8 — phí và bụi** | Bắt buộc tính 1,25% phí mỗi chiều, 0,002 SOL, trượt giá theo đúng cỡ vé, phí ưu tiên. Coin dưới 5 SOL là bụi, không bao giờ được nhắn | Bụi trông "sạch" (0 bẫy) nhưng chắc chắn lỗ: −3,7% dưới 1 SOL, −15% ở 1–5 SOL |
| **9 — đủ dữ liệu mới được phán** | Phát lại giao dịch từ 30 SOL phải ra đúng vSol được báo (sai số ≤ 1% hoặc 0,2 SOL), và phải có đủ giao dịch ở slot tạo. Thiếu thì ghi "THIẾU DỮ LIỆU". Độ phủ dưới 90% số lệnh tạo on-chain thì tạm dừng mọi output | PumpPortal chỉ chuyển khoảng một nửa số lệnh tạo |
| **10 — đối thủ thích nghi, luật chơi thay đổi** | Mỗi bộ lọc có phiên bản gắn với chương trình pump.fun đang chạy. Có chương trình mới thì treo tín hiệu MUA, bật lại mọi bộ lọc và kiểm lại. Giữ kín các bộ lọc | BOOST đẻ ra self-graduation chỉ sau vài tuần. Mô hình cửa sổ sớm mất tác dụng khi ra ngoài mẫu |
| **11 — một giả thuyết, đăng ký trước** | Đặt ngưỡng trên cửa sổ cũ, kiểm trên cửa sổ mới chưa nhìn. Mỗi lần chỉ một luật MUA chính. Không chỉnh ngưỡng trên dữ liệu forward. Mọi ô xem thêm đều phải ghi lại | Khoảng 200 ô đã được xem. Các kết quả dương chỉ có ở luật chọn sau và đảo chiều ở thời điểm khác |
| **12 — cỡ vé và trần lỗ** | Vé cố định và nhỏ (≤ 0,25–0,5 SOL), tối đa 5 lệnh mỗi ngày, có ngân sách thí điểm và điểm dừng (mất 30% ngân sách thì dừng). Mỗi tín hiệu hiển thị sẵn sàn lỗ trên curve | Phân phối đuôi dày, trung vị −30% đến −45% ở các tập có giao dịch |
| **13 — người vận hành** | Bot là cái phanh cho FOMO: không mua coin bot gắn TRÁNH, không mua coin bot chưa xem. Ghi giá khớp thật của mỗi lệnh để so với mô hình; lệch quá 5 điểm thì dừng | Người thêm độ trễ, trượt giá và hay làm trái bot. Giá trị dữ liệu ủng hộ nhất hiện nay là quyền phủ quyết |
| **14 — riêng tư và pháp lý** | Bot chỉ dùng riêng. Không chia sẻ, không bán tín hiệu, không nhận Callout Rewards. Theo dõi NĐ 284/2026 và hỏi luật sư trước khi chia sẻ | Chia sẻ biến người theo thành người cầm hàng cho mình thoát. Phát tín hiệu công khai có thể bị coi là quảng cáo, tiếp thị tài sản mã hoá không phép |
| **15 — công tắc tắt** | Cam kết trước: sau 60 ngày không có luật MUA nào đạt chuẩn thì bot vĩnh viễn chỉ cảnh báo | Không có điểm dừng định trước thì việc tìm tín hiệu mua biến thành đào bới dữ liệu vô tận |

## 5. Đặc tả v1

### Đầu ra

Bot **riêng tư, chỉ chủ bot dùng**. Bot **không bao giờ in chữ "MUA"** cho tới khi sổ bóng đạt chuẩn GO.

**(1) Kênh cảnh báo.** Bot trả lời khi chủ bot hỏi về một mint, và tự gắn nhãn các ứng viên còn sống lúc chúng được 2, 5 và 10 phút tuổi. Mỗi lần trả về đúng một trong ba dòng:

```
[TRÁNH] <SYMBOL> <mint4…4> | tuổi 5:00 | curve 18.3/85 SOL real | sàn lỗ trên curve −61% (+2.5% phí)
  | cờ: top10 34% (ngưỡng 20%); wash 41% volume (30%); dev giữ 6.1% chưa bán (3%)
  | cờ mạnh nhất: chênh mean forward −18 điểm [−27, −9], n=… | dữ liệu: khớp reserve 0.1%

[THIẾU DỮ LIỆU] <mint> | lý do: stream lệch reserve 3.4 SOL / mayhem / quote ≠ SOL / hết credit

[KHÔNG THẤY CỜ] <mint> | curve … SOL | sàn lỗ −…% | ĐÂY KHÔNG PHẢI TÍN HIỆU MUA.
  Tập không-cờ cùng tầng, 14 ngày qua: n=…, mean …% [KTC 95%], trung vị …%, thắng …%
```

**(2) Sổ bóng (ẩn với chủ bot).** Ghi mọi coin khớp luật mua B1: mint, thời điểm tín hiệu, giá curve ở slot kế tiếp, ở T+45 giây, ở T+90 giây, và kết quả. Chỉ sau khi đạt GO mới gửi:

```
[MUA THỬ] <mint> | vào ≤ 0.25 SOL trước t+90 s, bỏ nếu giá đã > +15% so với lúc báo
  | thoát: bán hết sau 30 phút, hoặc trong 60 s sau migration nếu curve hoàn tất, không giữ qua migration
  | sàn lỗ −…% | luật B1 forward: mean +…% [KTC], n=…
```

**(3) Bản tin hằng ngày lúc 00:00 UTC**, gồm:
- độ phủ dữ liệu;
- credit đã dùng;
- sổ của từng bộ lọc: số cờ, tỷ lệ bẫy có cờ / không cờ theo tầng, trung bình có cờ / không cờ, số coin thắng bị loại;
- số đếm của sổ bóng, không kèm phán quyết cho tới khi bài chạy thử kết thúc.

### Bộ lọc

**Tầng 0 (miễn phí, chặn từ đầu)**
- **Mayhem:** lệnh tạo có `is_mayhem_mode = true` → loại. Không bao giờ dùng địa chỉ curve của PumpPortal cho loại này.
- **Quote:** không phải SOL → loại.
- **Độ phủ:** phát lại giao dịch từ 30 SOL theo công thức curve.
  - Nếu lệch vSol được báo quá max(1%, 0,2 SOL) → THIẾU DỮ LIỆU.
  - Nếu thiếu giao dịch ở slot tạo, đọc bù một lần (10 credit); vẫn thiếu thì THIẾU DỮ LIỆU.
- **Self-graduation / bundle lấp curve:** creator và các ví mua ở slot tạo và slot kế đã mua ≥ 20 SOL thật, hoặc curve hoàn tất trước thời điểm quyết định → TRÁNH.

**Cổng F0 (xác định ứng viên, không phải bộ lọc bẫy):** ở 2, 5, 10 phút, cần đủ ba điều kiện:
- 5 ≤ SOL thật < 70;
- ≥ 5 giao dịch trong 120 giây gần nhất;
- ≥ 3 ví mua khác nhau trong 120 giây gần nhất.

Coin không qua cổng không được chấm, nhưng kết quả của nó vẫn được ghi.

**Tầng 1 (miễn phí, từ luồng giao dịch; ngưỡng đóng băng, không chỉnh)**
- top-10 (tính từ giao dịch) ≥ 20% cung;
- dev cộng creator giữ ròng ≥ 3%;
- wash: các ví đổi chiều mua/bán ≥ 3 lần chiếm ≥ 30% tổng SOL giao dịch;
- spike: SOL thật tăng ≥ 10 trong 60 giây;
- lướt nhanh: ≥ 8 ví bán trong vòng 5 slot sau lệnh mua của chính nó;
- ví bán mà không mua (nhận qua transfer) ≥ 0,5% cung;
- ví ở slot tạo còn giữ ≥ 5%.

**Tầng 2 (trả phí, tối đa 300 coin còn lại sau tầng 1 mỗi ngày)**
- **Ảnh chụp holder** (3 credit): phần nắm giữ ẩn = số dư thật trừ số dư suy từ giao dịch; cờ nếu ≥ 3% cung.
- **Cụm nguồn tiền** trên tối đa 8 ví (dev, ví ở slot tạo, top holder):
  - mỗi ví tốn khoảng 2–10 credit, có cache 30 ngày;
  - bỏ qua các ví nguồn đã nạp cho ≥ 20 mint khác nhau (sàn, dịch vụ);
  - cờ nếu cả cụm giữ ≥ 10% cung.

**Chỉ để thông tin, chưa gắn TRÁNH cho tới khi chứng minh được forward:**
- crew bán bám mua (đã kiểm soát mật độ lệnh);
- người tạo hàng loạt (≥ 3 mint trong 24 giờ);
- coin nhái ticker;
- volume gộp gấp ≥ 8 lần SOL ròng;
- người gọi kèo đã mua trước lúc gọi ở giá ≤ 0,5 lần giá hiện tại.

**Thăng / giáng nhãn:** một cờ ở tầng 1 hoặc 2 chỉ được gắn nhãn TRÁNH sau khi kiểm forward. Trước đó nó hiện là "cờ (chưa kiểm)".

**Luật mua B1** (chỉ trong sổ bóng, là giả thuyết duy nhất được đăng ký trước):
- thời điểm: 5 phút sau lệnh tạo;
- qua tầng 0 và cổng F0;
- SOL thật ≥ 5, top-10 < 20%, dev cộng creator giữ < 3%;
- vào ở T+45 giây;
- thoát sau 30 phút, hoặc bán vào pool trong 60 giây sau migration.

B1 được chọn từ chính các luật chọn sau khi xem dữ liệu ở mục 2. Vì vậy nó chỉ có giá trị khi đã kiểm forward.

### Thước đo

- **KPI chính:** trung bình lời/lỗ mỗi vé của sổ bóng B1 ở giá người thật khớp được:
  - giá curve ở T+45 giây, vé 0,25–0,5 SOL, phí 1,25% mỗi chiều, 0,002 SOL, có tính tác động giá của chính vé;
  - báo kèm KTC 95% bootstrap, hai nửa 7 ngày, trung vị, tỷ lệ thắng;
  - báo kèm trung bình sau khi bỏ 1% vé tốt nhất, và phần lãi mà 1% vé tốt nhất chiếm.
- **Độ nhạy theo độ trễ:** trung bình của B1 khi vào ở slot kế tiếp, T+45 giây và T+90 giây, ghép cặp trên cùng các coin.
- **Từng bộ lọc, chạy độc lập trên mọi ứng viên F0** (không chỉ trên coin sống sót sau các bộ lọc trước). Mỗi ngày ghi:
  - số cờ;
  - tỷ lệ bẫy có cờ / không cờ trong từng tầng curve, với KTC Wilson và lift;
  - chênh lệch trung bình có cờ / không cờ, với KTC bootstrap;
  - số coin thắng lớn (≥ +100%) bị loại so với số bẫy bị loại;
  - credit đã tốn.
- **Lỗ chuẩn hoá:** lỗ thực tế chia cho lỗ tối đa trên curve lúc vào, 1 − (30/(30+x))². Nhờ đó so sánh được tỷ lệ bẫy giữa các mức curve.
- **Độ phủ:** số lệnh tạo PumpPortal so với số lệnh tạo on-chain (lấy từ census hiện có), tỷ lệ ứng viên khớp reserve.
- **Bộ ghi đám đông nhận tín hiệu (kiểm luật 4):** với mỗi Pump Callout hoặc mục trending trên Dexscreener/GMGN, ghi:
  - khoảng cách từ lúc tạo coin tới lúc có tín hiệu;
  - giá ở 120 giây trước tín hiệu, lúc tín hiệu, sau 5 phút và sau 30 phút;
  - tỷ lệ SOL bán ra sau tín hiệu đến từ các ví đã mua trước đó.
- **Độ trôi:** lift và chênh lệch trung bình theo tuần, đánh dấu mỗi lần pump.fun đổi chương trình.
- **Người:** tỷ lệ tín hiệu được làm theo, giá khớp thật so với mô hình, số lần làm trái nhãn TRÁNH.

### Chạy thử trên giấy (sổ bóng)

**Chuẩn bị**
- Đăng ký trước: viết `PREREG-V1` (B1, lối thoát, ngưỡng cờ, quy tắc GO/NO-GO) và commit trước khi cửa sổ forward bắt đầu.
- Dữ liệu: toàn bộ luồng PumpPortal cộng đọc bù. Dự kiến khoảng 130–260 coin khớp B1 mỗi ngày.

**Cửa sổ:** cố định 14 ngày, chỉ đánh giá một lần ở cuối. Kiểm tra giữa chừng duy nhất là điểm dừng thảm hoạ: trung bình ≤ −10% khi n ≥ 200.

**B1 GO** (bật `[MUA THỬ]` và thí điểm thật với vé 0,25 SOL) chỉ khi đạt **tất cả**:
- n ≥ 400;
- trung bình ở T+45 giây ≥ +5% **và** cận dưới KTC 95% > 0. Với độ lệch chuẩn khoảng 0,75, thực tế cần trung bình khoảng +8% ở n ≈ 400;
- cả hai nửa 7 ngày đều có trung bình > 0;
- trung bình sau khi bỏ 1% vé tốt nhất vẫn > 0, **và** 1% vé tốt nhất chiếm < 50% tổng lãi;
- vào ở T+90 giây vẫn có trung bình > 0;
- phân phối lỗ chuẩn hoá không tệ hơn của F0.

**NO-GO** (bỏ B1, không chỉnh ngưỡng trên các ngày này):
- trung bình ≤ 0, **hoặc** cận trên KTC < +3%, **hoặc** một nửa ≤ −5%;
- mọi trường hợp lưng chừng (INCONCLUSIVE) cũng tính là bỏ;
- luật mới cần đăng ký mới trên những ngày chưa xem.

**Nhãn TRÁNH GO, cho từng cờ:** trong tầng ≥ 5 SOL, cần đủ các điều kiện:
- ≥ 200 cờ forward;
- trung bình có cờ trừ không cờ ≤ −10 điểm, với KTC bootstrap loại 0;
- cận dưới Wilson của lift > 1;
- tỷ lệ coin thắng bị loại trên bẫy bị loại không vượt tỷ lệ chung của tầng.

Thiếu điều kiện nào thì cờ chỉ để thông tin.

**Thí điểm thật sau GO:** vé 0,25 SOL, tối đa 5 lệnh mỗi ngày, ngân sách 10 SOL. Dừng khi mất 3 SOL, hoặc khi sau 50 vé trung bình thật thấp hơn mô hình quá 5 điểm.

### Chi phí

- **Helius:** trần cứng 30k credit mỗi ngày cho bot (khoảng 0,9 triệu mỗi tháng). Lấy từ trần 300k mỗi ngày của bộ ghi, hoặc mua thêm khoảng 1–2 triệu credit (khoảng $5–10 mỗi tháng theo giá trong đoạn trích, cần kiểm lại trên helius.dev).
- **Đơn giá và dự kiến mỗi ngày:**
  - tầng 0–1: 0 credit (websocket PumpPortal miễn phí);
  - đọc bù slot tạo: 10 credit, chỉ khi luồng bỏ sót (≤ 5k mỗi ngày);
  - tầng 2: tối đa 300 coin × khoảng 50 credit ≈ 15k mỗi ngày.
- **Khi chạm trần:** tầng 2 dừng và coin nhận nhãn THIẾU DỮ LIỆU. Bộ ghi dữ liệu không bao giờ bị lấy mất credit.
- **Không dùng máy quét trả phí bên thứ ba** (RugCheck, Birdeye, Bubblemaps, GMGN): không cái nào công bố độ chính xác trên pump.fun, và gói miễn phí quá nhỏ. Các kiểm tra chính của RugCheck (mint/freeze authority) vốn đã do chương trình pump.fun cố định.
- **Tổng chi phí thêm:** $0–10 mỗi tháng ngoài $49 đã trả, cộng khoảng 2–3 ngày công lập trình.

## 6. Kiểm chứng các khẳng định trong năm luật

| Khẳng định | Kết luận | Ghi chú |
|---|---|---|
| "86 nghìn ví mất 675K SOL" | **Không tìm thấy nguồn** | Khoảng 7 lần tìm có mục tiêu đều không ra. Các con số gần nhất có nguồn: (1) LIBRA, hơn 86% của 15.430 ví lỗ khoảng $251M (Nansen); rất có thể "86" là phần trăm chứ không phải số ví. (2) YZY, 51.862 ví lỗ $74,8M (Bubblemaps). (3) Dune: 56,6% của 4,26 triệu địa chỉ pump.fun lỗ $0–1k [S] |
| Chart có thể bị vẽ (crew bán bám mua) | **Đúng về loại hình**, mẫu cụ thể chưa thành bộ phát hiện | Wash-trade ít nhất 17% giao dịch pump.fun (CCS'26) [S]; 82,89% token tăng hơn 100% có tăng trưởng nhân tạo (USENIX Sec'26). Mẫu "bán bám mua" trên dữ liệu của mình: hiếm, gần như không có tác dụng ở 2 phút |
| PnL giả qua SPL-transfer vào ví trắng | **Cơ chế đúng**, chưa đo được mức phổ biến | Ví nhận token qua transfer có giá vốn $0 trên các công cụ tính PnL. Trên curve phát hiện được từ chính luồng giao dịch (ví bán nhiều hơn số đã mua): có ở 57% coin có lực lúc 2 phút |
| Funding graph, độ tập trung cung, thời điểm lệnh "không giả được" | **Sai** | Đắt để giả chứ không phải không giả được (xem luật 3) |
| Đi trước đám đông nhận tín hiệu 30–120 giây là đủ | **Chưa kiểm chứng**, và dữ liệu đi ngược | Không có nghiên cứu nào đo độ trễ này. KOL vào trong vài giây đầu [V]. Ở phút 2–10 không còn đà tăng |
| Chạy được trên Helius $49 | **Đúng một phần** | Gói Developer là $49, 10 triệu credit, 50 rps [S]. Chỉ đủ khi lọc theo tầng và có trần 30k mỗi ngày. LaserStream gRPC chỉ có từ gói Business |
| Bỏ sót token tốt giá bằng 0 | Đúng với từng token, **sai với cả chiến lược** | Lời nằm ở số ít coin tăng mạnh |
| Nuốt bẫy giá bằng cả position | **Sai trên curve, đúng sau migration** | Trên curve lỗ có sàn: −44% ở 10 SOL, −75% ở 30 SOL |
| Tỷ lệ nền "98–99% là bẫy" | **Phụ thuộc định nghĩa** | Solidus Labs: 99% là pump-and-dump hoặc rug [S]; arXiv 2603.24625: 76%. Census của mình với định nghĩa riêng: 7,6–13% ở các coin còn giao dịch, 39–45% ở tầng ≥ 5 SOL |
| Callout Rewards trả USDC theo volume | **Nguồn mâu thuẫn** | Invezz và CoinEx nói USDC, Bittime nói token PUMP, AInvest nói không có thưởng [S] |
| NĐ 284/2026 | **Có thật** | Ban hành 16/7/2026, hiệu lực 1/9/2026. Mức phạt cao nhất 200 triệu (tổ chức) / 100 triệu (cá nhân). Giao dịch ngoài đơn vị được cấp phép: 30–50 triệu, chỉ áp dụng sau 6 tháng kể từ khi có đơn vị đầu tiên được cấp phép (theo VnFinance). Quảng cáo, tiếp thị tài sản mã hoá không phép: 180–200 triệu với tổ chức. Không tìm thấy điều khoản riêng về "tín hiệu" [S] |

## 7. Tiêu chí dừng (kill)

- **Sổ bóng B1:**
  - trung bình ở T+45 giây ≤ 0 khi n ≥ 400 sau 14 ngày → bỏ B1 vĩnh viễn, không chỉnh lại ngưỡng trên cùng các ngày đó;
  - lưng chừng (trung bình > 0 nhưng cận dưới KTC ≤ 0, hoặc dưới +5%) → bỏ. Lợi thế quá nhỏ để phát hiện ở n ≈ 400–1.500 thì cũng quá nhỏ để người thật bắt được sau trượt giá và sai sót;
  - phụ thuộc đuôi (1% vé tốt nhất chiếm ≥ 50% lãi, hoặc bỏ chúng đi thì trung bình ≤ 0) → bỏ;
  - độ trễ: vào ở T+90 giây có trung bình ≤ 0 → bỏ.
- **Thay đổi chế độ thị trường:**
  - một nửa 7 ngày có trung bình ≤ −5%, hoặc điểm dừng thảm hoạ kích hoạt → bỏ;
  - pump.fun đổi chương trình (thưởng, phí, BOOST, tham số curve) → treo `[MUA THỬ]` ngay, bật lại mọi bộ lọc, chạy lại sổ bóng chỉ trên dữ liệu sau thay đổi.
- **Dữ liệu:** độ phủ < 90% quá 24 giờ, hoặc > 5% ứng viên không khớp reserve → tạm dừng mọi output, kể cả kênh cảnh báo.
- **Thí điểm thật:** mất ≥ 3 SOL trên ngân sách 10 SOL, hoặc trung bình thật thấp hơn mô hình quá 5 điểm sau 50 vé → dừng giao dịch thật, quay về sổ bóng.
- **Cờ cảnh báo:** sau ≥ 200 cờ trong tầng ≥ 5 SOL mà KTC chênh lệch trung bình vẫn chứa 0 → hạ xuống chỉ để thông tin. Cờ miễn phí không bao giờ bị xoá; cờ trả phí chỉ bị xoá khi người duyệt.
- **Ngân sách:** bot vượt 30k credit mỗi ngày 3 ngày liền → tắt tầng 2.
- **Dự án:** sau 60 ngày không có luật MUA nào đạt GO → bot vĩnh viễn chỉ cảnh báo, ngừng tìm tín hiệu mua trên curve.
- **Pháp lý và đạo đức:** có bất kỳ kế hoạch chia sẻ, bán tín hiệu, hay nhận Callout Rewards → dừng và hỏi luật sư theo NĐ 284/2026 trước.

## 8. Kết luận

Năm luật tốt hơn phần lớn các "hệ thống" memecoin ngoài kia, vì chúng nghi ngờ mặt tiền và đòi đo lường. Nhưng dữ liệu nói rõ hai điều:
1. Loại bẫy thì dễ, còn tìm ra tập "đáng mua" có lời trung bình thì chưa ai làm được ở tốc độ con người.
2. Thứ có giá trị thật ngay bây giờ là **quyền phủ quyết**: chặn những cú mua FOMO vào coin có dấu hiệu bẫy rõ ràng, kèm sàn lỗ và chất lượng dữ liệu của từng coin.

Bản v1 vì vậy là bot cảnh báo riêng tư, cộng một bài kiểm forward duy nhất cho luật mua. Nếu B1 bị KILL như dự kiến, đó là một câu trả lời có giá trị, có được trước khi mất tiền thật.

## Nguồn

**Bài báo**
- [Meme Coin Factories (CCS'26)](https://arxiv.org/abs/2609.10246)
- [Catching the Rug (arXiv 2608.20271)](https://arxiv.org/abs/2608.20271)
- [Kamat, graduation audit](https://arxiv.org/abs/2607.02823)
- [MELT / MemeTrans](https://arxiv.org/abs/2602.13480)
- [Mongardini & Mei (USENIX Sec'26)](https://arxiv.org/pdf/2507.01963)
- [Luo et al., copy-trading (WWW'26)](https://arxiv.org/abs/2601.08641)
- [arXiv 2603.24625](https://arxiv.org/abs/2603.24625)

**Phân tích và báo chí**
- [Pine Analytics: Exit Liquidity Machines](https://pineanalytics.substack.com/p/exit-liquidity-machines)
- [Blockworks: ví phối hợp trong ICO PUMP](https://blockworks.com/news/pump-fun-ico-coordinated-wallet)
- [BeInCrypto: phần lớn trader pump.fun lỗ](https://beincrypto.com/pump-fun-trading-data-majority-lose-money/)
- [HTX: chỉ khoảng 6% trader memecoin Solana có lời](https://www.htx.com/news/what-are-the-odds-only-6-of-solana-meme-traders-made-a-profi-5gTkabXy/)
- [Coinspeaker: LIBRA](https://www.coinspeaker.com/libra-meme-coin-losses-shoot-251-million-86-traders-lost-money/)
- [Solidus Labs: Solana rug pulls](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance)
- [Protos: $700K cho người gọi kèo](https://protos.com/pump-fun-paid-700k-to-callers-shilling-mostly-tiny-tokens/)

**Hạ tầng**
- [Helius: các gói dịch vụ](https://www.helius.dev/docs/billing/plans.md)
- [Helius: credit](https://docs.helius.xyz/docs/billing/credits.md)
- [Helius: LaserStream](https://www.helius.dev/docs/faqs/laserstream)
- [Birdeye: giá](https://docs.birdeye.so/docs/pricing)
- [Bubblemaps API](https://docs.bubblemaps.io/data/api/authentication.md)

**Pháp lý (Việt Nam)**
- [LSVN: mức phạt theo NĐ 284/2026](https://lsvn.vn/cac-muc-xu-phat-vi-pham-hanh-chinh-ve-tai-san-ma-hoa-va-thi-truong-tai-san-ma-hoa-a177706.html)
- [VnFinance: từ 1/9 nhà đầu tư cá nhân đối mặt nguy cơ bị phạt](https://vietnamfinance.vn/sau-1-9-ca-nhan-dau-tu-tai-san-ma-hoa-doi-dien-nguy-co-dinh-nhieu-an-phat-d149946.html)
- [VnFinance: cung cấp dịch vụ không phép bị phạt tới 200 triệu](https://vietnamfinance.vn/cung-cap-dich-vu-tai-san-ma-hoa-khong-phep-bi-phat-toi-200-trieu-dong-d147775.html)

**Dữ liệu của dự án**
- `docs/SNIPER.md`, `docs/RESEARCH.md`.
- Các script thăm dò của agent dữ liệu nằm ở thư mục scratch của phiên (`scratchpad/sieve/`). Chúng chưa được đưa vào repo; khi xây v1 sẽ viết lại thành mã có test.
