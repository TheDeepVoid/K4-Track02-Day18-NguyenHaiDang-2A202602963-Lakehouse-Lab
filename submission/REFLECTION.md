# Reflection (Bài suy ngẫm)

**Anti-pattern được chọn:** *"Treating the Data Lake as a Data Dump"* (Xem Data Lake như một kho chứa thô, đổ dữ liệu vô tội vạ mà không có kiểm soát)

## 1. Anti-pattern này là gì?

Anti-pattern này xảy ra khi đội ngũ chỉ tập trung vào việc "ingest càng nhanh càng tốt", đổ toàn bộ dữ liệu thô (logs, events, raw files...) vào một layer duy nhất (thường là Bronze) mà bỏ qua các ràng buộc về schema, validation, phân vùng (partitioning), vòng đời dữ liệu (lifecycle) và governance. Kết quả là hệ thống nhanh chóng trở thành một "data swamp" (đầm lầy dữ liệu) - khó truy vấn, khó bảo trì và khó đảm bảo an toàn dữ liệu.

## 2. Vì sao hệ thống/dữ liệu tôi quan tâm dễ gặp phải nó?

Trong lĩnh vực AI/LLM observability (tương tự Topic A trong bonus), hệ thống có đặc điểm rất dễ rơi vào anti-pattern này:

- **Khối lượng dữ liệu khổng lồ:** Với 1B requests/ngày (~5 TB/ngày), áp lực về tốc độ ingestion thường cao hơn rất nhiều so với áp lực về chất lượng dữ liệu. Điều này dẫn đến xu hướng "dump first, clean later".
- **Dữ liệu phi cấu trúc phức tạp:** Logs LLM (prompt, response, tool calls, reasoning traces) rất đa dạng về schema, dễ thay đổi liên tục giữa các model versions. Các đội ngũ thường ngại áp dụng schema enforcement vì sợ làm gián đoạn ingestion.
- **Tốc độ phát triển nhanh:** Khi feature/model thay đổi liên tục, việc thiếu process để quản lý schema evolution có thể khiến đội ngũ chọn giải pháp "schema-on-read" hoàn toàn mà không có bất kỳ ràng buộc nào tại thời điểm ghi.
- **Thiếu FinOps từ đầu:** Nếu không tính toán chi phí storage/computation ngay từ thiết kế, việc lưu trữ toàn bộ prompt/response trong thời gian dài (dù không cần thiết cho analytics) sẽ làm chi phí tăng nhanh chóng.

## 3. Cách phòng tránh

Để phòng tránh anti-pattern này, cần áp dụng các nguyên tắc đã học trong Day 18:

- **Áp dụng Medallion Architecture:** Không lưu tất cả ở một layer. Bronze giữ raw immutable (với checksum, metadata), Silver làm sạch/standardize (dedup, normalize, PII tokenization), Gold cung cấp aggregates tối ưu cho từng use case (cost/latency dashboards).
- **Schema Enforcement + Evolution có kiểm soát:** Sử dụng Delta Lake schema enforcement tại write để chặn dữ liệu không hợp lệ, kết hợp schema evolution có chủ đích (explicit mergeSchema) thay vì cho phép mọi thay đổi tự động.
- **Data Lifecycle & Tiering:** Xây dựng retention policy rõ ràng (vd. full traces 7 ngày, aggregates 1 năm) và áp dụng lifecycle/compaction định kỳ để tránh tình trạng "small files explosion".
- **Governance từ đầu:** Tokenize/redact PII tại Bronze landing, ghi nhận lineage (audit log) cho mọi truy cập dữ liệu nhạy cảm, và áp dụng RBAC trên từng layer.
- **Measure, don't assume:** Theo dõi chi phí (FinOps), file counts, scan sizes như các metrics đầu tiên - không chỉ latency/availability.

## 4. Phạm vi sử dụng AI

Trong quá trình thực hiện bài lab này, tôi đã sử dụng AI như một công cụ hỗ trợ học tập:
- **Hỗ trợ hiểu khái niệm:** Giải thích các khái niệm phức tạp (Delta vs Iceberg, hidden partitioning, vector search, provenance) để nắm bắt nhanh hơn.
- **Hỗ trợ định dạng & viết tài liệu:** Giúp chỉnh sửa ngôn ngữ, cấu trúc Markdown cho rõ ràng, nhất quán.
- **Không sinh code cốt lõi:** Toàn bộ code trong notebooks, scripts, tests đều được đọc-hiểu, chạy và xác thực thủ công. AI chỉ hỗ trợ diễn giải, không tự viết để vượt qua các yêu cầu bắt buộc.

Chi tiết sử dụng AI được ghi trong `submission/AI_USAGE.md`.
