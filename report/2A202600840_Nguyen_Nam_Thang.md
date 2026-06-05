# Báo Cáo Lab 7: Embedding & Vector Store

**Họ tên:** Nguyen Nam Thang  
**MSSV:** 2A202600840  
**Nhóm:** Viettel FAQ Retrieval  
**Ngày:** 05/06/2026

---

## 1. Warm-up (5 điểm)

### Cosine Similarity (Ex 1.1)

**High cosine similarity nghĩa là gì?**  
High cosine similarity nghĩa là hai vector có hướng gần giống nhau trong không gian embedding, nên nội dung văn bản thường có ý nghĩa gần nhau. Với text embeddings, điểm càng gần 1 thì hai câu càng có khả năng nói về cùng chủ đề hoặc cùng intent.

**Ví dụ HIGH similarity:**
- Sentence A: Khách hàng muốn kiểm tra gói Mobile Internet trên MyViettel.
- Sentence B: Người dùng cần xem lưu lượng data còn lại trong ứng dụng My Viettel.
- Tại sao tương đồng: Cả hai đều nói về tra cứu gói data/lưu lượng trên MyViettel.

**Ví dụ LOW similarity:**
- Sentence A: Khách hàng muốn kiểm tra gói Mobile Internet trên MyViettel.
- Sentence B: Hóa đơn điện tử được ký bằng chữ ký số.
- Tại sao khác: Hai câu thuộc hai domain khác nhau: app di động và hóa đơn doanh nghiệp.

**Tại sao cosine similarity được ưu tiên hơn Euclidean distance cho text embeddings?**  
Cosine similarity tập trung vào hướng của vector, phù hợp để so sánh ý nghĩa văn bản dù độ lớn vector khác nhau. Euclidean distance dễ bị ảnh hưởng bởi magnitude, trong khi embeddings thường cần đo mức gần nhau về nghĩa hơn là độ dài vector.

### Chunking Math (Ex 1.2)

**Document 10,000 ký tự, chunk_size=500, overlap=50. Bao nhiêu chunks?**  
Step size = 500 - 50 = 450.  
Số chunks = ceil((10000 - 500) / 450) + 1 = ceil(9500 / 450) + 1 = 22 + 1 = **23 chunks**.

**Nếu overlap tăng lên 100, chunk count thay đổi thế nào? Tại sao muốn overlap nhiều hơn?**  
Step size giảm còn 400 nên số chunk tăng: ceil((10000 - 500) / 400) + 1 = 25 chunks. Overlap nhiều hơn giúp giữ context giữa hai chunk liền kề, nhưng làm tăng số vector cần lưu và search.

---

## 2. Document Selection — Nhóm (10 điểm)

### Domain & Lý Do Chọn

**Domain:** Viettel customer support FAQ, gồm MyViettel, Mobile, Internet-TV, Digital Application, Business Service và Shop.

**Tại sao nhóm chọn domain này?**  
Bộ FAQ Viettel có cấu trúc rõ ràng theo dạng câu hỏi/trả lời, rất phù hợp để thử nghiệm retrieval. Domain này cũng có nhiều nhánh dịch vụ khác nhau, nên metadata như `domain`, `doc_id`, `language` có ích khi lọc kết quả trước khi search.

### Data Inventory

| # | Tên tài liệu | Nguồn | Số ký tự | Metadata đã gán |
|---|--------------|-------|----------|-----------------|
| 1 | Viettel - Business Service FAQs.md | Local `data/` | 42,513 | `doc_id=viettel_business_service_faqs`, `domain=business`, `language=vi` |
| 2 | Viettel - Digital Application FAQs.md | Local `data/` | 13,724 | `doc_id=viettel_digital_application_faqs`, `domain=digital`, `language=vi` |
| 3 | Viettel - Internet - TV FAQs.md | Local `data/` | 67,696 | `doc_id=viettel_internet_tv_faqs`, `domain=internet`, `language=vi` |
| 4 | Viettel - Mobile FAQs.md | Local `data/` | 66,587 | `doc_id=viettel_mobile_faqs`, `domain=mobile`, `language=vi` |
| 5 | Viettel - MyViettel FAQs.md | Local `data/` | 18,992 | `doc_id=viettel_myviettel_faqs`, `domain=digital`, `language=vi` |
| 6 | Viettel - Shop Viettet FAQs.md | Local `data/` | 4,452 | `doc_id=viettel_shop_faqs`, `domain=shop`, `language=vi` |

### Metadata Schema

| Trường metadata | Kiểu | Ví dụ giá trị | Tại sao hữu ích cho retrieval? |
|----------------|------|---------------|-------------------------------|
| `doc_id` | string | `viettel_myviettel_faqs` | Lọc chính xác theo tài liệu gốc, dùng khi domain quá rộng. |
| `domain` | string | `digital`, `internet`, `business` | Giảm nhiễu bằng cách search trong đúng nhóm dịch vụ. |
| `source` | string | `Viettel - MyViettel FAQs.md` | Truy vết câu trả lời về file gốc. |
| `language` | string | `vi` | Hữu ích nếu sau này có dữ liệu nhiều ngôn ngữ. |
| `chunk_id` | string | `viettel_myviettel_faqs_chunk_0` | Định danh từng chunk trong vector store. |
| `heading_path` | string | `Viettel - MyViettel FAQs > Q: ...` | Giữ context cấu trúc Markdown/FAQ. |

---

## 3. Chunking Strategy — Cá nhân chọn, nhóm so sánh (15 điểm)

### Baseline Analysis

Chạy `ChunkingStrategyComparator().compare()` trên 3 tài liệu, `chunk_size=1000`:

| Tài liệu | Strategy | Chunk Count | Avg Length | Preserves Context? |
|-----------|----------|-------------|------------|-------------------|
| MyViettel FAQs | FixedSizeChunker | 19 | 999.6 | Trung bình, có thể cắt giữa câu hỏi/trả lời |
| MyViettel FAQs | SentenceChunker | 33 | 571.0 | Tốt hơn theo câu nhưng chưa hiểu heading FAQ |
| MyViettel FAQs | RecursiveChunker | 21 | 889.9 | Tốt, giữ đoạn tốt hơn fixed-size |
| Mobile FAQs | FixedSizeChunker | 67 | 993.8 | Dễ cắt ngang câu hỏi dài |
| Mobile FAQs | SentenceChunker | 157 | 420.4 | Nhiều chunk nhỏ, dễ mất context |
| Mobile FAQs | RecursiveChunker | 76 | 864.6 | Cân bằng hơn |
| Internet-TV FAQs | FixedSizeChunker | 68 | 995.5 | Chưa khai thác cấu trúc Markdown |
| Internet-TV FAQs | SentenceChunker | 149 | 451.9 | Tách nhỏ, đôi khi thiếu phần answer |
| Internet-TV FAQs | RecursiveChunker | 79 | 848.0 | Tốt hơn fixed-size |

### Strategy Của Tôi

**Loại:** Custom strategy - `MarkdownStructureChunker`

**Mô tả cách hoạt động:**  
Strategy này tách Markdown theo heading `#`, `##`, `###` trước, vì file FAQ dùng heading để biểu diễn từng câu hỏi. Mỗi section giữ cả câu hỏi và câu trả lời bên dưới, giúp chunk có ngữ nghĩa hoàn chỉnh hơn. Nếu một section quá dài, strategy fallback sang `RecursiveChunker` để chia tiếp nhưng vẫn thêm dòng context `[Markdown path: ...]`. Khi dùng `chunk_with_metadata()`, mỗi chunk có thêm `chunk_index`, `chunk_id`, `heading_path`, `section_title`.

**Tại sao tôi chọn strategy này cho domain nhóm?**  
FAQ Viettel có cấu trúc rất rõ: tiêu đề file là `#`, mỗi câu hỏi là `### Q: ...`, câu trả lời nằm ngay bên dưới. Vì vậy tách theo document structure sẽ tốt hơn fixed-size, tránh cắt rời câu hỏi khỏi câu trả lời. Metadata `heading_path` cũng giúp trace kết quả retrieval về đúng mục FAQ.

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
| MyViettel FAQs | RecursiveChunker baseline | 21 | 889.9 | Ít chunk hơn nhưng có section dài bị chia chưa gắn heading rõ |
| MyViettel FAQs | **MarkdownStructureChunker** | 32 | 614.0 | Tốt hơn cho FAQ vì giữ heading câu hỏi |
| Mobile FAQs | RecursiveChunker baseline | 76 | 864.6 | Cân bằng nhưng chưa biết ranh giới Q/A |
| Mobile FAQs | **MarkdownStructureChunker** | 149 | 464.9 | Nhiều chunk hơn nhưng mỗi chunk gần với một Q/A |
| Internet-TV FAQs | RecursiveChunker baseline | 79 | 848.0 | Tốt cho đoạn văn dài |
| Internet-TV FAQs | **MarkdownStructureChunker** | 142 | 492.9 | Trace source tốt hơn nhờ `heading_path` |

### So Sánh Với Thành Viên Khác

| Thành viên | Strategy | Retrieval Score (/10) | Điểm mạnh | Điểm yếu |
|-----------|----------|----------------------|-----------|----------|
| Tôi | MarkdownStructureChunker + metadata filter | 4/10 tạm tính với `_mock_embed` | Giữ cấu trúc FAQ, metadata rõ | Mock embedding không hiểu nghĩa tiếng Việt tốt |
| Thành viên khác | Chưa có dữ liệu nhóm | Chưa đánh giá | Chưa có | Chưa có |
| Thành viên khác | Chưa có dữ liệu nhóm | Chưa đánh giá | Chưa có | Chưa có |

**Strategy nào tốt nhất cho domain này? Tại sao?**  
Với dữ liệu FAQ Markdown, strategy tốt nhất về mặt thiết kế là document-structure based chunking. Nó tận dụng ranh giới tự nhiên của tài liệu, giữ câu hỏi và câu trả lời gần nhau, đồng thời metadata giúp filter theo domain hoặc truy vết nguồn.

---

## 4. My Approach — Cá nhân (10 điểm)

### Chunking Functions

**`SentenceChunker.chunk` — approach:**  
Tôi dùng regex `(?<=[.!?])\s+` để tách câu theo dấu kết thúc câu rồi gom tối đa `max_sentences_per_chunk` câu vào một chunk. Edge case: text rỗng trả về list rỗng, tham số nhỏ hơn 1 được ép về 1.

**`RecursiveChunker.chunk` / `_split` — approach:**  
Thuật toán thử separator theo thứ tự `\n\n`, `\n`, `. `, space, rồi fallback fixed-size. Base case là text rỗng hoặc độ dài nhỏ hơn `chunk_size`. Nếu một phần vẫn quá dài, hàm gọi đệ quy với separator nhỏ hơn.

**`MarkdownStructureChunker` — approach:**  
Tôi thêm strategy custom cho Markdown bằng cách parse heading `#` đến `######`. Mỗi section được giữ nguyên heading path; nếu section quá dài thì fallback sang recursive split nhưng vẫn thêm context Markdown path vào chunk.

### EmbeddingStore

**`add_documents` + `search` — approach:**  
Mỗi `Document` được chuyển thành record gồm `id`, `content`, `metadata`, `embedding`. Store ưu tiên dùng ChromaDB nếu cài được; nếu không thì fallback về in-memory. Khi search, code embed query rồi query ChromaDB hoặc tính cosine similarity trong list fallback.

**`search_with_filter` + `delete_document` — approach:**  
Filter được áp dụng trước retrieval bằng metadata filter. Với ChromaDB, filter đi qua `where`; với fallback in-memory thì lọc bằng so sánh exact match trên metadata. `delete_document` xóa tất cả records có `metadata["doc_id"] == doc_id`.

### KnowledgeBaseAgent

**`answer` — approach:**  
Agent gọi `store.search(question, top_k)` để lấy context, sau đó ghép các chunks thành prompt có source. Prompt yêu cầu trả lời chỉ dựa trên context và nói không biết nếu context không đủ, rồi gọi `llm_fn(prompt)`.

### Test Results

```text
python3 -m pytest tests/ -v
42 passed in 0.55s
```

**Số tests pass:** 42 / 42

---

## 5. Similarity Predictions — Cá nhân (5 điểm)

Kết quả actual dùng `_mock_embed`, nên score không phản ánh ngữ nghĩa tiếng Việt tốt như embedding thật.

| Pair | Sentence A | Sentence B | Dự đoán | Actual Score | Đúng? |
|------|-----------|-----------|---------|--------------|-------|
| 1 | MyViettel kiểm tra gói data | Ứng dụng My Viettel hiển thị gói Mobile Internet và lưu lượng còn lại | high | 0.0508 | Một phần |
| 2 | Đăng ký gói 4G | Soạn tin nhắn tên gói cước gửi 191 để đăng ký | high | -0.0964 | Không |
| 3 | Hóa đơn điện tử doanh nghiệp | Doanh nghiệp có thể tra cứu và sử dụng hóa đơn điện tử | high | -0.1161 | Không |
| 4 | Lắp internet gia đình | Dịch vụ Internet và truyền hình Viettel hỗ trợ khách hàng gia đình | high | 0.0537 | Một phần |
| 5 | Cách đăng nhập MyViettel | Cửa hàng bán điện thoại iPhone và phụ kiện | low | 0.0034 | Có |

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn nghĩa?**  
Cặp "Đăng ký gói 4G" và "Soạn tin nhắn gửi 191" đáng lẽ phải khá gần nhưng `_mock_embed` cho điểm âm. Điều này cho thấy mock embedding chỉ hữu ích cho test kỹ thuật, không nên dùng để kết luận chất lượng semantic retrieval thật.

---

## 6. Results — Cá nhân (10 điểm)

Benchmark chạy trên `MarkdownStructureChunker(chunk_size=1200)` + `EmbeddingStore` dùng ChromaDB + `_mock_embed`. Tổng số chunks lưu trong vector store: **446**.

### Benchmark Queries & Gold Answers

| # | Query | Gold Answer |
|---|-------|-------------|
| 1 | Tôi dùng BankPlus chuyển tiền nhầm thì có lấy lại tiền được không? | Chỉ lấy lại được khi có sự đồng ý của người nhận; liên hệ tổng đài BankPlus 1900 8099 để được tư vấn. |
| 2 | Camera Viettel có phân biệt chuyển động giữa người và vật không? | Camera trong nhà không phân biệt; camera ngoài trời dùng AI để phân biệt chuyển động người/vật. |
| 3 | Hóa đơn điện tử là gì? | Tập hợp thông điệp dữ liệu điện tử về bán hàng/cung ứng dịch vụ, lập và quản lý bằng phương tiện điện tử, ký số, có giá trị pháp lý. |
| 4 | Truyền hình cáp Viettel có chia được cho nhiều tivi không? | Có thể kéo một đường dây cáp chia cho nhiều tivi; thuê bao tivi thứ hai trở đi rẻ hơn. |
| 5 | Tôi không đăng nhập được app MyViettel thì phải làm gì? | Kiểm tra mạng 3G/4G, đăng nhập bằng OTP/3G/4G/mật khẩu hoặc gọi tổng đài hỗ trợ. |

### Kết Quả Của Tôi

| # | Query | Top-1 Retrieved Chunk (tóm tắt) | Score | Relevant? | Agent Answer (tóm tắt) |
|---|-------|--------------------------------|-------|-----------|------------------------|
| 1 | BankPlus chuyển tiền nhầm | Đúng section BankPlus chuyển tiền nhầm | 0.301 | Có | Trả lời dựa trên context BankPlus |
| 2 | Camera phân biệt người/vật | Trả về section MyViettel không liên quan | 0.307 | Không | Context không đủ để trả lời đúng |
| 3 | Hóa đơn điện tử là gì | Đúng section Hóa đơn điện tử là gì | 0.304 | Có | Trả lời được từ context hóa đơn |
| 4 | Truyền hình cáp chia nhiều tivi | Trả về section truyền hình cáp liên quan nhu cầu nhiều thế hệ/nhiều tivi | 0.331 | Một phần | Có context gần nhưng chưa đúng nhất |
| 5 | Không đăng nhập được MyViettel | Trả về section tra cứu thời hạn gói Mobile Internet | 0.295 | Không | Context không đúng vấn đề đăng nhập |

**Bao nhiêu queries trả về chunk relevant trong top-3?** 2 / 5 chắc chắn, 1 / 5 partial.

**Nhận xét:**  
Metadata filter giúp giảm nhiễu theo domain, nhưng `domain=digital` vẫn còn rộng vì chứa cả MyViettel, BankPlus, Camera. Với embedding thật, kết quả sẽ tốt hơn; với `_mock_embed`, retrieval semantic tiếng Việt còn nhiễu. Nếu cải thiện tiếp, tôi sẽ dùng `LocalEmbedder` hoặc OpenAI embeddings và filter thêm `doc_id` khi user chọn rõ nhóm dịch vụ.

---

## 7. What I Learned (5 điểm — Demo)

**Điều hay nhất tôi học được từ thành viên khác trong nhóm:**  
Chưa có dữ liệu so sánh nhóm tại thời điểm viết báo cáo. Phần này sẽ được bổ sung sau khi nhóm chạy cùng 5 benchmark queries với các strategy khác nhau.

**Điều hay nhất tôi học được từ nhóm khác (qua demo):**  
Chưa có dữ liệu demo liên nhóm tại thời điểm viết báo cáo. Dự kiến tôi sẽ so sánh cách các nhóm chọn metadata và cách họ xử lý tài liệu dài.

**Nếu làm lại, tôi sẽ thay đổi gì trong data strategy?**  
Tôi sẽ chuẩn hóa domain chi tiết hơn, ví dụ tách `digital_application`, `myviettel`, `bankplus`, `camera` thay vì gom chung `digital`. Tôi cũng sẽ dùng embedding thật cho tiếng Việt để đánh giá retrieval quality chính xác hơn thay vì dựa vào `_mock_embed`.

---

## Tự Đánh Giá

| Tiêu chí | Loại | Điểm tự đánh giá |
|----------|------|-------------------|
| Warm-up | Cá nhân | 5 / 5 |
| Document selection | Nhóm | 9 / 10 |
| Chunking strategy | Nhóm | 13 / 15 |
| My approach | Cá nhân | 10 / 10 |
| Similarity predictions | Cá nhân | 4 / 5 |
| Results | Cá nhân | 7 / 10 |
| Core implementation (tests) | Cá nhân | 30 / 30 |
| Demo | Nhóm | 2 / 5 |
| **Tổng** | | **80 / 100** |
