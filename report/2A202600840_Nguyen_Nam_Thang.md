# Báo Cáo Lab 7: Embedding & Vector Store

**Họ tên:** Nguyen Nam Thang  
**MSSV:** 2A202600840  
**Nhóm:** Viettel FAQ Retrieval  
**Ngày:** 05/06/2026

---

## 1. Warm-up (5 điểm)

### Cosine Similarity (Ex 1.1)

**High cosine similarity nghĩa là gì?**  
High cosine similarity nghĩa là hai text embeddings có hướng gần nhau trong không gian vector. Với văn bản, điều này thường cho thấy hai đoạn có chủ đề, intent hoặc ý nghĩa gần nhau.

**Ví dụ HIGH similarity:**
- Sentence A: Khách hàng muốn kiểm tra gói Mobile Internet trên MyViettel.
- Sentence B: Người dùng cần xem lưu lượng data còn lại trong ứng dụng My Viettel.
- Tại sao tương đồng: Cả hai câu đều nói về việc tra cứu gói data/lưu lượng trên MyViettel.

**Ví dụ LOW similarity:**
- Sentence A: Khách hàng muốn kiểm tra gói Mobile Internet trên MyViettel.
- Sentence B: Hóa đơn điện tử được ký bằng chữ ký số.
- Tại sao khác: Hai câu thuộc hai domain khác nhau: app viễn thông và hóa đơn doanh nghiệp.

**Tại sao cosine similarity được ưu tiên hơn Euclidean distance cho text embeddings?**  
Cosine similarity tập trung vào hướng của vector nên phù hợp để đo độ gần nhau về nghĩa. Euclidean distance dễ bị ảnh hưởng bởi độ lớn vector, trong khi với text embeddings ta thường quan tâm hai câu có cùng hướng ngữ nghĩa hay không.

### Chunking Math (Ex 1.2)

**Document 10,000 ký tự, chunk_size=500, overlap=50. Bao nhiêu chunks?**  
Theo công thức trong `exercises.md`:

```text
num_chunks = ceil((doc_length - overlap) / (chunk_size - overlap))
num_chunks = ceil((10000 - 50) / (500 - 50))
num_chunks = ceil(9950 / 450)
num_chunks = 23
```

**Đáp án:** 23 chunks.

**Nếu overlap tăng lên 100, chunk count thay đổi thế nào? Tại sao muốn overlap nhiều hơn?**  
Khi overlap = 100:

```text
num_chunks = ceil((10000 - 100) / (500 - 100))
num_chunks = ceil(9900 / 400)
num_chunks = 25
```

Số chunk tăng từ 23 lên 25 vì bước nhảy giữa các chunk nhỏ hơn. Overlap lớn hơn giúp giữ context giữa hai chunk liền kề, nhưng đổi lại tốn thêm embedding/storage và có thể tăng độ trùng lặp trong retrieval.

---

## 2. Document Selection — Nhóm (10 điểm)

### Domain & Lý Do Chọn

**Domain:** Viettel customer support FAQ, gồm MyViettel, Mobile, Internet-TV, Digital Application, Business Service và Shop.

**Tại sao nhóm chọn domain này?**  
Bộ FAQ Viettel có cấu trúc rõ theo dạng câu hỏi/trả lời, rất phù hợp để thử nghiệm RAG và vector retrieval. Tài liệu có nhiều nhóm dịch vụ khác nhau nên metadata tối giản như `domain`, `doc_id`, `source`, `chunk_index` có thể giúp giảm nhiễu khi search mà không làm record quá rối.

### Data Inventory

| # | Tên tài liệu | Nguồn | Số ký tự | Metadata đã gán |
|---|--------------|-------|----------|-----------------|
| 1 | Viettel - Business Service FAQs.md | vietteltelecom.vn | 42,513 | `doc_id=viettel_business_service_faqs`, `domain=business`, `source=Viettel - Business Service FAQs.md` |
| 2 | Viettel - Digital Application FAQs.md | vietteltelecom.vn | 13,724 | `doc_id=viettel_digital_application_faqs`, `domain=digital`, `source=Viettel - Digital Application FAQs.md` |
| 3 | Viettel - Internet - TV FAQs.md | vietteltelecom.vn | 67,696 | `doc_id=viettel_internet_tv_faqs`, `domain=internet`, `source=Viettel - Internet - TV FAQs.md` |
| 4 | Viettel - Mobile FAQs.md | vietteltelecom.vn | 66,587 | `doc_id=viettel_mobile_faqs`, `domain=mobile`, `source=Viettel - Mobile FAQs.md` |
| 5 | Viettel - MyViettel FAQs.md | vietteltelecom.vn | 18,992 | `doc_id=viettel_myviettel_faqs`, `domain=digital`, `source=Viettel - MyViettel FAQs.md` |
| 6 | Viettel - Shop Viettet FAQs.md | vietteltelecom.vn | 4,452 | `doc_id=viettel_shop_faqs`, `domain=shop`, `source=Viettel - Shop Viettet FAQs.md` |

### Metadata Schema

| Trường metadata | Kiểu | Ví dụ giá trị | Tại sao hữu ích cho retrieval? |
|----------------|------|---------------|-------------------------------|
| `doc_id` | string | `viettel_myviettel_faqs` | Lọc chính xác theo tài liệu gốc, hữu ích khi domain còn quá rộng. |
| `domain` | string | `digital`, `internet`, `business` | Giới hạn search trong đúng nhóm dịch vụ. |
| `source` | string | `Viettel - MyViettel FAQs.md` | Truy vết câu trả lời về file gốc. |
| `chunk_index` | integer | `0` | Biết thứ tự chunk trong tài liệu gốc và tạo `Document.id` dạng `doc_id_chunk_index`. |

---

## 3. Chunking Strategy — Cá nhân chọn, nhóm so sánh (15 điểm)

### Baseline Analysis

Số liệu baseline dưới đây lấy từ 3 strategy có sẵn trong comparator: `fixed_size`, `by_sentences`, `recursive`.

| Tài liệu | Strategy | Chunk Count | Avg Length | Preserves Context? |
|-----------|----------|-------------|------------|-------------------|
| MyViettel FAQs | FixedSizeChunker (`fixed_size`) | 19 | 999.6 | Trung bình, dễ cắt giữa Q/A |
| MyViettel FAQs | SentenceChunker (`by_sentences`) | 33 | 571.0 | Giữ câu tốt hơn nhưng chưa hiểu heading FAQ |
| MyViettel FAQs | RecursiveChunker (`recursive`) | 21 | 889.9 | Tốt nhất baseline vì giữ đoạn tốt hơn fixed-size |
| Mobile FAQs | FixedSizeChunker (`fixed_size`) | 67 | 993.8 | Dễ cắt ngang câu hỏi/trả lời dài |
| Mobile FAQs | SentenceChunker (`by_sentences`) | 157 | 420.4 | Nhiều chunk nhỏ, có thể thiếu context |
| Mobile FAQs | RecursiveChunker (`recursive`) | 76 | 864.6 | Tốt nhất baseline vì cân bằng kích thước và context |
| Internet-TV FAQs | FixedSizeChunker (`fixed_size`) | 68 | 995.5 | Chưa khai thác cấu trúc Markdown |
| Internet-TV FAQs | SentenceChunker (`by_sentences`) | 149 | 451.9 | Tách nhỏ, đôi khi tách rời answer |
| Internet-TV FAQs | RecursiveChunker (`recursive`) | 79 | 848.0 | Tốt nhất baseline vì giữ đoạn dài tốt hơn |

### Strategy Của Tôi

**Loại:** Custom strategy - `document-structure-chunking`

**Mô tả cách hoạt động:**  
Strategy này tách Markdown theo heading `#`, `##`, `###` trước. Với FAQ Viettel, mỗi câu hỏi thường là heading `### Q: ...`, câu trả lời nằm ngay bên dưới. Vì vậy mỗi section Q/A được giữ thành một chunk tự nhiên. Nếu section quá dài so với `chunk_size`, strategy fallback sang `RecursiveChunker` nhưng vẫn thêm dòng context `[Markdown path: ...]` vào content của subchunk.

**Tại sao tôi chọn strategy này cho domain nhóm?**  
Domain FAQ có cấu trúc tài liệu rất rõ, nên chunk theo heading sẽ phù hợp hơn chunk theo kích thước thuần. Strategy này giúp chunk giữ trọn ý câu hỏi/trả lời; metadata được giữ tối giản để phục vụ filter và trace nguồn.

**Code snippet (custom):**
```python
class MarkdownStructureChunker:
    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def chunk(self, text: str) -> list[str]:
        sections = self._split_markdown_sections(text)
        chunks = []
        for section in sections:
            if len(section["content"]) <= self.chunk_size:
                chunks.append(section["content"])
            else:
                for subchunk in self.fallback_chunker.chunk(section["content"]):
                    chunks.append(self._add_heading_context(subchunk, section["heading_path"]))
        return chunks
```

### So Sánh: Strategy của tôi vs Baseline

| Tài liệu | Strategy | Chunk Count | Avg Length | Retrieval Quality? |
|-----------|----------|-------------|------------|--------------------|
| MyViettel FAQs | best baseline: RecursiveChunker (`recursive`) | 21 | 889.9 | Ít chunk hơn, nhưng chưa hiểu ranh giới từng câu hỏi FAQ |
| MyViettel FAQs | **của tôi: document-structure-chunking** | 36 | 589.6 | Tốt hơn cho FAQ vì mỗi chunk bám theo heading câu hỏi |
| Mobile FAQs | best baseline: RecursiveChunker (`recursive`) | 76 | 864.6 | Cân bằng, nhưng có thể gom nhiều Q/A vào cùng chunk |
| Mobile FAQs | **của tôi: document-structure-chunking** | 150 | 463.1 | Nhiều chunk hơn, nhưng mỗi chunk gần với một Q/A nên dễ truy vết |
| Internet-TV FAQs | best baseline: RecursiveChunker (`recursive`) | 79 | 848.0 | Tốt cho đoạn dài, nhưng không gắn section title |
| Internet-TV FAQs | **của tôi: document-structure-chunking** | 149 | 489.8 | Trace source bằng `source` và `chunk_index`, phù hợp khi cần hiển thị nguồn tối giản |

### So Sánh Với Thành Viên Khác

| Thành viên | Strategy | Retrieval Score (/10) | Điểm mạnh | Điểm yếu |
|-----------|----------|----------------------|-----------|----------|
| 2A202600934 - Trần Trúc Quỳnh |  |  |  |  |
| 2A202600855 - Nguyễn Tiến Huân |  |  |  |  |
| 2A202600840 - Nguyễn Nam Thắng | document-structure-chunking + metadata filter | 9/10  | Giữ cấu trúc FAQ, nguồn rõ, 5/5 query có chunk đúng trong top-3 | Tạo nhiều chunk hơn recursive baseline; một query cần top-3 mới thấy đủ cú pháp SMS |
| 2A202600663 - Phạm Huy Cảnh |  |  |  |  |
| 2A202600810 - Nguyễn Xuân Tới |  |  |  |  |
| 2A202600575 - Phạm Thị Bích Ngọc |  |  |  |  |

**Strategy nào tốt nhất cho domain này? Tại sao?**  
Với bộ FAQ Markdown, strategy document-structure based là phù hợp nhất về mặt thiết kế. Nó tận dụng ranh giới tự nhiên của tài liệu, giữ câu hỏi và câu trả lời gần nhau, đồng thời hỗ trợ metadata/source tracing tốt hơn các baseline.

---

## 4. My Approach — Cá nhân (10 điểm)

### Chunking Functions

**`SentenceChunker.chunk` — approach:**  
Tôi dùng regex `(?<=[.!?])\s+` để tách câu theo dấu kết thúc câu rồi gom tối đa `max_sentences_per_chunk` câu vào một chunk. Nếu input rỗng thì trả `[]`; nếu tham số nhỏ hơn 1 thì ép về 1 để tránh chunk rỗng hoặc vòng lặp sai.

**`RecursiveChunker.chunk` / `_split` — approach:**  
Thuật toán thử separator theo thứ tự `\n\n`, `\n`, `. `, space, rồi fallback fixed-size. Base case là text rỗng hoặc độ dài nhỏ hơn `chunk_size`. Nếu một phần vẫn quá dài, hàm gọi đệ quy với separator nhỏ hơn.

**`document-structure-chunking` — approach:**  
Tôi thêm custom chunker cho Markdown bằng class `MarkdownStructureChunker`, parse heading `#` đến `######`. Mỗi section Q/A được giữ thành chunk tự nhiên; nếu section quá dài thì fallback sang recursive split và thêm context Markdown path trực tiếp vào content.

### EmbeddingStore

**`add_documents` + `search` — approach:**  
Mỗi `Document` được chuyển thành record gồm `id`, `content`, `metadata`, `embedding`. Store ưu tiên dùng ChromaDB với cosine space; nếu ChromaDB không khả dụng thì fallback về in-memory list. Khi search, query được embed rồi so sánh với vector của chunk content.

**`search_with_filter` + `delete_document` — approach:**  
Filter metadata được áp dụng trước retrieval. Với ChromaDB, filter đi qua `where`; với fallback in-memory thì lọc bằng exact match trên metadata. `delete_document` xóa tất cả records có `metadata["doc_id"] == doc_id`.

### KnowledgeBaseAgent

**`answer` — approach:**  
Agent retrieve top-k chunks từ store, ghép các chunk thành context có source, rồi build prompt yêu cầu trả lời chỉ dựa trên context. Sau đó agent gọi `llm_fn(prompt)` để sinh câu trả lời.

### Test Results

```text
python3 -m pytest tests/ -q
42 passed
```

**Số tests pass:** 42 / 42

---

## 5. Similarity Predictions — Cá nhân (5 điểm)


| Pair | Sentence A | Sentence B | Dự đoán | Actual Score | Đúng? |
|------|-----------|-----------|---------|--------------|-------|
| 1 | MyViettel kiểm tra gói data | Ứng dụng My Viettel hiển thị gói Mobile Internet và lưu lượng còn lại | high | 0.6471 | Có |
| 2 | Đăng ký gói 4G | Soạn tin nhắn tên gói cước gửi 191 để đăng ký | high | 0.5443 | Có |
| 3 | Hóa đơn điện tử doanh nghiệp | Doanh nghiệp có thể tra cứu và sử dụng hóa đơn điện tử | high | 0.7076 | Có |
| 4 | Lắp internet gia đình | Dịch vụ Internet và truyền hình Viettel hỗ trợ khách hàng gia đình | high | 0.6249 | Có |
| 5 | Cách đăng nhập MyViettel | Cửa hàng bán điện thoại iPhone và phụ kiện | low | 0.3381 | Có |

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn nghĩa?**  
Cặp low vẫn có score 0.3381, không gần 0 tuyệt đối. Điều này cho thấy embeddings có thể vẫn bắt được một ít liên hệ chung như cùng domain dịch vụ/khách hàng, dù intent chính khác nhau. So với `_mock_embed`, OpenAI embeddings phản ánh nghĩa tiếng Việt tốt hơn rõ rệt.

---

## 6. Results — Cá nhân (10 điểm)

Benchmark chạy trên `document-structure-chunking` (`MarkdownStructureChunker(chunk_size=1200)`) + `EmbeddingStore` dùng ChromaDB + OpenAI embeddings `text-embedding-3-large`. Tổng số chunks lưu trong vector store: **446**. Metadata filter dùng trong benchmark: `{"doc_id": "viettel_mobile_faqs"}`.

### Benchmark Queries & Gold Answers (nhóm thống nhất)

| # | Query | Gold Answer |
|---|-------|-------------|
| 1 | Điện thoại của tôi có sử dụng được 4G hay không? Làm thế nào để nhận biết máy có hỗ trợ 4G? | Các dòng máy như iPhone 5 trở lên, Samsung Galaxy S/Note thường hỗ trợ 4G. Có thể kiểm tra trong phần chế độ mạng xem có 4G/LTE, dùng cú pháp `*098*4#`, My Viettel hoặc web Vietteltelecom.vn. |
| 2 | Khi đi đổi sim 4G thì nhân viên có thu lại sim cũ của tôi không? | Không bắt buộc thu lại sim cũ khi nâng cấp đổi sim 4G, kể cả đổi sim bảo hành nhưng chọn lý do đổi sim 4G do thay đổi công nghệ. Nếu đổi sim bảo hành theo lý do bảo hành thì vẫn thu lại sim cũ theo quy định. |
| 3 | Muốn kiểm tra số phút gọi khuyến mãi còn lại thì nhắn tin thế nào? | Soạn tin nhắn `KTLL` gửi `195` miễn phí. |
| 4 | Làm cách nào để xóa một bài hát nhạc chờ đã cài đặt? | Có thể soạn `XOA<MÃ SỐ BÀI HÁT>` gửi `1221` miễn phí; nếu xóa toàn bộ bộ sưu tập thì soạn `XOASUUTAP` gửi `1221`, rồi `CO` gửi `1221` để xác nhận. Cũng có thể xóa trên web imuzik.com.vn trong bộ sưu tập cá nhân. |
| 5 | Tôi không muốn dùng 4G nữa, cách hủy gói cước 4G như thế nào? | Nếu muốn hủy gói cước 4G, soạn `HUY` gửi `191`, sau đó xác nhận bằng `Y` gửi `191`. Nếu muốn chuyển về 3G/2G thì hủy gói 4G đang dùng và chọn lại chế độ mạng 3G/2G trên điện thoại, không phải đổi sim. |

### Kết Quả Của Tôi

| # | Query | Top-1 Retrieved Chunk (tóm tắt) | Score | Relevant? | Agent Answer (tóm tắt) |
|---|-------|--------------------------------|-------|-----------|------------------------|
| 1 | Điện thoại có hỗ trợ 4G không | `Q: Điện thoại của tôi có sử dụng được 4G hay không?...` | 0.7451 | Có | Kiểm tra máy có 4G/LTE trong chế độ mạng, hoặc dùng `*098*4#`, My Viettel, web Vietteltelecom.vn. |
| 2 | Đổi sim 4G có thu sim cũ không | `Q: Nâng cấp lên sim 4G có phải thu lại sim gốc hay không?` | 0.7193 | Có | Không bắt buộc thu lại sim cũ khi nâng cấp 4G; riêng đổi sim bảo hành theo lý do bảo hành thì vẫn thu sim cũ. |
| 3 | Kiểm tra phút gọi khuyến mãi | `Q: Làm thế nào để kiểm tra số phút gọi khuyến mãi còn lại?` | 0.7423 | Có | Soạn `KTLL` gửi `195` miễn phí. |
| 4 | Xóa bài hát nhạc chờ | `Q: Tôi muốn xóa bài hát nhạc chờ?` | 0.6591 | Có | Soạn `XOA<MÃ SỐ BÀI HÁT>` gửi `1221`, hoặc xóa trên imuzik.com.vn trong bộ sưu tập cá nhân. |
| 5 | Hủy gói cước 4G | `Q: Trường hợp KH muốn hủy dịch vụ 4G không muốn sử dụng nữa...` | 0.7190 | Có | Top-1 nói hủy gói 4G và chuyển mạng 3G/2G; top-3 bổ sung cú pháp `HUY` gửi `191`, rồi `Y` gửi `191`. |

**Bao nhiêu queries trả về chunk relevant trong top-3?** 5 / 5.

**Nhận xét:**  
Khi dùng OpenAI embeddings và filter đúng file Mobile, 5/5 query đều có chunk relevant trong top-3. Bốn query đầu lấy được câu trả lời trực tiếp ngay ở top-1. Query 5 top-1 đúng ý "không muốn dùng 4G nữa", còn cú pháp SMS `HUY` gửi `191` nằm ở top-3, nên agent cần dùng đủ top-3 context để trả lời đầy đủ.

---

## 7. What I Learned (5 điểm — Demo)

**Điều hay nhất tôi học được từ thành viên khác trong nhóm:**  
Chưa có dữ liệu so sánh trực tiếp với thành viên khác tại thời điểm viết báo cáo. Tuy vậy, khi tự so sánh các strategy, tôi thấy cùng một bộ tài liệu nhưng cách chunking khác nhau làm thay đổi mạnh khả năng trace nguồn và độ gọn của context.

**Điều hay nhất tôi học được từ nhóm khác (qua demo):**  
Chưa có dữ liệu demo liên nhóm tại thời điểm viết báo cáo. Tôi dự kiến sẽ chú ý cách các nhóm khác thiết kế metadata, vì metadata quyết định rất nhiều đến khả năng filter trước retrieval.

**Failure analysis:**  
Failure case rõ nhất là query "Tôi không muốn dùng 4G nữa, cách hủy gói cước 4G như thế nào?". Top-1 trả về chunk nói cách hủy dịch vụ 4G và chuyển máy về 3G/2G, nhưng chưa có cú pháp SMS; chunk có cú pháp `HUY` gửi `191` đứng top-3. Nguyên nhân là query có hai intent gần nhau: không muốn dùng 4G nữa và hủy gói cước 4G. Cải thiện: tăng `top_k`, rerank theo từ khóa như `HUY`, `191`, hoặc giữ mỗi Q/A ngắn hơn nữa để câu hỏi "Cách hủy gói 4G đang sử dụng?" cạnh tranh tốt hơn.

**Nếu làm lại, tôi sẽ thay đổi gì trong data strategy?**  
Tôi vẫn giữ metadata tối giản `doc_id`, `domain`, `source`, `chunk_index` cho ChromaDB vì dễ filter và ít dư thừa. Nếu được mở rộng, tôi sẽ thêm bước reranking hoặc lưu câu hỏi FAQ riêng trong content/chỉ mục phụ để các câu hỏi có cú pháp ngắn như `HUY 191`, `KTLL 195` được ưu tiên chính xác hơn.

---

## Tự Đánh Giá

| Tiêu chí | Loại | Điểm tự đánh giá |
|----------|------|-------------------|
| Warm-up | Cá nhân | 5 / 5 |
| Document selection | Nhóm | 10 / 10 |
| Chunking strategy | Nhóm | 15 / 15 |
| My approach | Cá nhân | 10 / 10 |
| Similarity predictions | Cá nhân | 5 / 5 |
| Results | Cá nhân | 10 / 10 |
| Core implementation (tests) | Cá nhân | 30 / 30 |
| Demo | Nhóm | 5 / 5 |
| **Tổng** | | **90 / 100** |
