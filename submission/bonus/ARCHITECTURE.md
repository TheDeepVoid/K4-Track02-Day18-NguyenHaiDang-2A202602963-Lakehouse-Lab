# Bonus Challenge - Architecture Design: A. LLM Observability ở quy mô 1B requests/ngày

**Học viên:** Nguyễn Hải Đăng  
**MSSV:** 2A202602963  
**Topic:** A - LLM Observability at scale 1B requests/day  
**Thời gian thiết kế:** 4–6 giờ (architecture brief)

## 1. Problem Statement (≤200 từ)

Một foundation-model API team cần log mọi request/response để phục vụ observability. Các con số và ràng buộc:

- **Scale:** 1B requests/ngày, ~5 KB/request → ~5 TB/ngày raw (uncompressed)
- **(1) Cost & latency dashboard:** Refresh mỗi 5 phút, filter theo tenant
- **(2) Full prompt/response:** Giữ 7 ngày để incident review
- **(3) Aggregates only:** Sau 7 ngày, chỉ giữ aggregates trong 1 năm
- **(4) PII protection:** Phải redact PII trước khi bất kỳ ai đọc được
- **Budget:** Tổng chi phí storage ≤ $5,000/tháng (across all tiers)
- **Constraints thêm:** Hoạt động offline-friendly không phụ thuộc external SaaS; cần audit trail cho truy cập PII; tránh "data swamp"; scale write/read đều lớn

**Vì sao khó?**
- Trade-off giữa giữ full traces (debugging quan trọng) và budget $5K/tháng
- PII xuất hiện trong prompt/response đa dạng (emails, phone numbers, IDs) - cần tokenize tại ingestion trước khi lưu vào shared storage
- Hot path: dashboards cần p95 low latency với filter theo tenant, nhưng scan 5TB/ngày là tốn kém nếu không tối ưu
- Lifecycle phức tạp: phải chuyển tier (hot→warm→cold) đúng thời điểm mà vẫn đảm bảo truy xuất khi cần incident review

## 2. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            LLM OBSERVABILITY LAKEHOUSE                          │
└─────────────────────────────────────────────────────────────────────────────────┘

INGESTION (Streaming + Batch backfill)
┌─────────────────────┐
│  API Gateway Logs   │───►[Debezium-style/EventStream]───► Bronze Landing (raw immutable)
└─────────────────────┘                                        │
                                                               ▼
                                              ┌─────────────────────────────────────┐
QUERY PATHS                                        │ BRONZE (Landing Zone)              │
┌─────────────┐                                    │ - Immutable raw events (Avro/JSON) │
│ Dashboards   │───► Gold (Aggregates)◄────────────│ - PII detection + tokenization    │
│ (5-min refresh)                                   │ - Write-ahead checksums            │
└─────────────┘                                    │ - Schema-on-write enforced         │
       │                                            │ - Partitioned by event_date/hour   │
       │                                            └─────────────┬─────────────────────┘
       │                                                          │ (Bronze→Silver)
       │                                                          ▼
       │                                            ┌─────────────────────────────────────┐
AD-HOC/INCIDENT                                      │ SILVER (Cleansed & Normalized)     │
┌─────────────┐                                    │ - PII tokenized (no raw PII)       │
│ Security/    │───► Silver (7-day full)◄─────────│ - Deduplication (request_id+ts)    │
│ Incident     │                                    │ - Standardized schema (strict)     │
│ Review Team  │                                    │ - Enriched with tenant/org         │
└─────────────┘                                    │ - Z-order by (tenant, api_key_hash)│
                                                    │ - Compacted (avoid small files)    │
                                                    └─────────────┬─────────────────────┘
                                                                  │ (Silver→Gold)
                                                                  ▼
                                                    ┌─────────────────────────────────────┐
                                                    │ GOLD (Business Aggregates)         │
                                                    │ - Cost: sum($) by tenant/hour/day  │
                                                    │ - Latency: p50/p95/p99 by route   │
                                                    │ - Tokens: in/out by model/tenant   │
                                                    │ - Partitioned by date (iceberg)    │
                                                    │ - Optimized for low-cardinality    │
                                                    │ - Retained 1 year (aggregates)     │
                                                    └─────────────────────────────────────┘

CONTROL PLANE (Day18 concepts applied):
- Catalog: Apache Iceberg REST Catalog (vendor-neutral) for Gold/Warm; Delta Lake for Bronze/Silver hot
- ACID: MERGE/DELETE/UPDATE for compaction, dedup, lifecycle rules
- Time Travel: enable on Silver/Bronze for reproducible incident investigation (≤7d for full)
- Lineage: OpenLineage events from Bronze→Silver→Gold + audit log for PII-access
- Governance: RBAC by role (analyst vs security-incident), column-level masking at read

## 3. Quyết định chính kèm alternatives đã loại (≥5 decisions, mỗi ≥2 alternatives)

### DECISION 1: Table Format (Hybrid: Delta Lake + Apache Iceberg)
- **Chọn:** Hybrid - **Delta Lake** cho Bronze/Silver (hot, streaming ingestion, heavy MERGE/compaction, CDC-style dedup) + **Apache Iceberg** cho Gold (aggregates, cold/warm tiering, vendor-neutral for future BI engines)
- **Loại B: Pure Iceberg everywhere** - trade-off: pyiceberg/delta-rs ergonomics cho streaming-heavy path (Bronze/Silver) phức tạp hơn; Delta CDF + eager small-file handling mạnh hơn cho 5TB/day streaming. Cost: ops overhead cao hơn.
- **Loại C: Pure Delta everywhere** - trade-off: vendor lock-in (catalog semantics) hạn chế multi-engine (Trino/Presto/DuckDB) đọc Gold tier long-term; Iceberg REST catalog + metadata tree tốt hơn cho lifecycle across heterogeneous engines. Governance portability yếu.

**Áp dụng Day18:** table formats, catalogs, ACID semantics.

### DECISION 2: PII Redaction/Tokenization tại Bronze (Shift-left security)
- **Chọn:** **Tokenize tại Bronze landing** (deterministic tokenization, salted per tenant) trước khi bất kỳ pipeline downstream ghi dữ liệu chia sẻ. Raw PII KHÔNG lưu trong Silver/Gold.
- **Loại B: Redact sau Silver (downstream)** - trade-off: blast radius lớn (nhiều consumers có thể thấy PII trước khi cleanup). Rủi ro compliance (Nghị định 13/2023/NĐ-CP) cao, khó prove "redacted before any read".
- **Loại C: Schema-on-read masking chỉ ở BI layer** - trade-off: dữ liệu PII vẫn tồn tại ở storage (lake) accessible to multiple roles/jobs; audit completeness khó đảm bảo, tăng surface attack. Cost/storage vẫn giữ PII dư thừa.

**Áp dụng Day18:** Security/Governance, lineage, medallion (Bronze gatekeeper).

### DECISION 3: Partitioning Strategy (Hot-path filter by tenant + time)
- **Chọn:** **Partition by `event_date` (day) + `hour`** tại Bronze/Silver, kèm **Z-order by `(tenant_id, request_route)`** (hoặc clustering). Gold partition by `agg_date` (day). Tránh over-partitioning (thousands of small partitions).
- **Loại B: Partition by tenant_id (high-cardinality)** - trade-off: 10^4–10^5 tenants → partition explosion, small files, list/scan planning chậm, compaction khó. Compute + metadata overhead >> benefit.
- **Loại C: Partition chỉ theo hour (ignore tenant)** - trade-off: dashboard filter "by tenant" mỗi 5 phút sẽ scan toàn bộ hour across tenants → I/O lớn, vi phạm latency target khi scale. Scan amplification cao.

**Áp dụng Day18:** Z-order/clustering, partitioning strategy, query optimization.

### DECISION 4: Data Lifecycle & Retention (Tiering để đạt $5K/tháng)
- **Chọn:** **3-tier lifecycle:** (a) Bronze/Silver full-traces hot/warm 0–7 ngày (local/fast storage), (b) Silver-truncated/Warm 7–30 ngày (infrequent access), (c) **Gold aggregates only** >7 ngày giữ 1 năm (cold, columnar compressed). **Delete full raw PII-containing fields after 7 days** (soft-delete markers + time-travel window giới hạn).
- **Loại B: Giữ full traces 30+ ngày** - trade-off: 5TB/ngày × 30 ngày = ~150TB active; với $5K cap, unit cost cần < $2.8/TB/month (impossible for hot storage + backups). Budget constraint bị vi phạm rõ ràng.
- **Loại C: Giữ raw prompts/response vô thời hạn** - trade-off: cost grows linearly, compliance risk (retention principle: chỉ giữ cần thiết), tăng blast radius PII. FinOps vi phạm hoàn toàn.

**Back-of-envelope (storage):** 5TB/day raw, after tokenization+column pruning+compression ~1.5–2.0TB/day effective for full traces (7d) + aggregates ~50–500GB/day rolled to year → total ~30–40TB peak, target <$5K/mo feasible với cold tiering. (Chi tiết §5)

**Áp dụng Day18:** FinOps tiering, retention/lifecycle, medallion (separating concerns).

### DECISION 5: Compaction, Small Files & Write Optimization
- **Chọn:** **Target file size 128–512 MB** (columnar). Schedule **OPTIMIZE** (Delta) + **rewrite_data_files** (Iceberg) 2–4x/ngày cho hot partitions (today-last3h), async cho older. Combine with **Z-order by (tenant, route)** cho hot filter path.
- **Loại B: No compaction, write many small files (streaming)** - trade-off: metadata overhead lớn, file listing chậm, scan amplification cao → dashboard 5-min refresh dễ miss SLA; query cost tăng nhanh.
- **Loại C: Compaction aggressive (realtime)** - trade-off: compute cost cao, write amplification, có thể ảnh hưởng ingestion throughput peak (30K writes/sec). Trade-off không cân bằng với 5-min refresh requirement.

**Áp dụng Day18:** ACID (OPTIMIZE), compaction cadence, performance.

### DECISION 6: Catalog, Lineage & Audit (Reproducibility + Zero-vendor lock-in)
- **Chọn:** **Apache Iceberg REST Catalog** (vendor-neutral) làm control plane chính cho Gold + shared metadata; Bronze/Silver dùng Delta với catalog mapping. **OpenLineage + audit table** (PII-access log: who/when/why/columns). **Time Travel** enabled trên Silver/Bronze (window ≤7 ngày full-traces) để incident replay.
- **Loại B: Lock-in vào single vendor catalog** - trade-off: migration risk (topic F), giới hạn engine choice (Trino/DuckDB/Spark), khó đạt vendor-neutral goal dài hạn.
- **Loại C: No lineage/audit, chỉ rely on logs** - trade-off: không thể trả lời "ai đã đọc PII khi nào?" một cách xác thực (compliance/audit). Incident forensics thiếu reproducibility; không đáp ứng governance requirement.

**Áp dụng Day18:** Catalogs (Iceberg REST), lineage (OpenLineage), time travel, governance.

## 4. Failure Modes (≥3), detection & rollback

### FM-1: PII Leakage (Critical) – 3 AM
- **Scenario:** Tokenization bug (regex missed pattern) ghi raw email/phone vào Silver shared path.
- **Detection:** 
  - Schema contract checks (forbidden columns: `prompt_raw_pii`, `email`, `phone_raw` must not exist in Silver/Gold)
  - Data quality rules: scan sampled rows nightly + realtime sampling (PII regex scan) on write path
  - Audit anomaly: unexpected read of columns marked sensitive
- **Rollback:** 
  1. **Quarantine:** Copy affected partitions to `bronze/quarantine/YYYY-MM-DD/` (immutable)
  2. **Time Travel:** RESTORE Silver table to last known-good snapshot (before bad write) 
  3. **Backfill:** Reprocess quarantined Bronze events with fixed tokenizer (idempotent MERGE)
  4. **Verify:** Re-run contract checks + confirm no PII in Silver/Gold
- **Tie to Day18:** schema enforcement/evolution, time travel (RESTORE), lineage/audit.

### FM-2: Small-Files Explosion – ingestion spike at peak
- **Scenario:** Sudden traffic spike (30K→100K writes/sec burst) tạo hàng triệu small Parquet files (<32MB). Dashboards 5-min refresh chậm, metadata bloated.
- **Detection:**
  - Metrics: `files_per_partition` > threshold (e.g. >500 files for last hour)
  - Query latency: dashboard p95 > 5 phút threshold
  - File size histogram alert (median < 64MB)
- **Rollback/Remediation:**
  1. **Throttle/queue:** Backpressure ingestion (pause non-critical batch)
  2. **Async OPTIMIZE:** Run `OPTIMIZE` with predicate on hot partitions (target 128–256MB). For Iceberg Gold: `rewrite_data_files`
  3. **Auto-scaling compaction:** Spin dedicated compaction jobs (separate from query cluster)
  4. **Verify:** files_pruned ratio ≥ 5–10× (like NB2) before resuming full query load
- **Tie to Day18:** OPTIMIZE + Z-order, compaction, ACID transactions.

### FM-3: Corrupted/Bad Write breaking Silver→Gold transform – 3 AM
- **Scenario:** Upstream schema change (new field type) or data corruption causes Silver transform to produce wrong aggregates (cost numbers inflated).
- **Detection:**
  - Data contracts: row count sanity (Silver rows ≈ Bronze deduped), null % spikes
  - Business metrics anomaly: e.g. cost/req jumps > 2σ vs 7-day rolling
  - Transform failure rate > 1%, or CDF mismatch
- **Rollback:**
  1. **Freeze Gold writes:** Pause Silver→Gold job
  2. **Time Travel:** RESTORE Gold to last known-good version (before corruption)
  3. **Fix transform:** Rollback pipeline code/config to last-good
  4. **Idempotent replay:** Recompute affected agg_date ranges from Silver (MERGE with dedup by natural key). Verify checksum vs old good snapshot.
- **Tie to Day18:** time travel (RESTORE), schema enforcement/evolution, ACID (MERGE), medallion isolation.

### FM-4: Catalog/Metadata Inconsistency (Iceberg REST)
- **Scenario:** REST Catalog write partially fails during snapshot commit (network timeout) → metadata pointer inconsistent.
- **Detection:** Snapshot chain validation (previous_snapshot_id continuity), missing manifest files, or engines see different snapshot IDs.
- **Rollback:** 
  1. **Read-only mode** for affected tables
  2. **Inspect metadata tree** (like NB5) to identify last valid snapshot
  3. **Rollback to valid snapshot** via catalog (set current_snapshot to last-good). Do NOT rewrite data files.
  4. **Repair:** Re-register if needed; verify cross-engine consistency (Trino/DuckDB) before re-enabling writes.
- **Tie to Day18:** Iceberg metadata tree, catalogs, time travel semantics.

## 5. Ước lượng chi phí back-of-envelope (show math)

### Assumptions (conservative)
- Raw ingest: 5 TB/ngày, 30 ngày/month → 150 TB raw written/month (ingestion)
- After tokenization + column pruning (drop verbose debug fields) + Snappy/Zstd: effective size factor ~0.35–0.40 for full traces → ~1.75 TB/day full-traces stored while hot
- Aggregates: ~50–200 GB/day rolled/compressed, 1-year retention
- Retention split: full traces 7d (hot), truncated 8–30d (warm), aggregates-only >30d (cold)
- Representative cloud storage $/TB-mo (order-of-magnitude): Hot (Standard/GP3-like) ~$23/TB/mo, Warm (IA/Infrequent) ~$12/TB/mo, Cold (Archive/Glacier-like) ~$4/TB/mo. Compute separate.

### Storage breakdown

**(A) Full traces (Bronze+Silver) 0–7 days (hot)**
- Effective ~1.8 TB/day × 7 days = ~12.6 TB peak (hot tier)
- $12.6 TB × $23/TB/mo ≈ **$290/mo**

**(B) Warm/truncated 8–30 days (warm, optional - avoid if tight)**
- Truncate: keep only essential columns (no full prompts beyond sampling?) or move to warm. Assume 30% of full size: 0.54 TB/day × 23 days = ~12.4 TB? Better to delete full PII-rich traces after 7d. Design: **delete full request/response bodies after 7d**, keep only metadata+aggregates. 
- If we strictly follow requirement (2): "prompt/response đầy đủ giữ 7 ngày" and (3): "sau đó chỉ giữ aggregates 1 năm" → **no full traces > 7d**. So B=0.

**(C) Aggregates Gold 1 year (cold)**
- Aggregates ~100 GB/day compressed × 365 days = ~36.5 TB? Or ~100GB/day * 365 = 36500GB = 36.5TB? 100GB/day × 365 = 36.5TB. Maybe conservative 200GB/day → 73TB. But likely smaller (pre-aggregated, high-cardinality dims rolled up). Assume **50 GB/day → 18.25 TB/year** (cold)
- $18.25 TB × $4/TB/mo effective (cold/tiered) ≈ **$73/mo**

**(D) Metadata, manifests, logs (small)** ~0.5–1 TB total ≈ **$10–$20/mo**

**Subtotal storage ≈ $290 + $73 + $20 = ~$383/mo**

**(E) Compute (back-of-envelope)** 
- Ingestion/streaming: continuous, small
- Compaction (OPTIMIZE): 2–4x/day, ~10–20 CPU-hours/day ≈ ~$20–$40/day max in peak? Or amortized ~$300–$600/mo
- Dashboards 5-min refresh + ad-hoc: mostly scan Gold (small) + occasional Silver 7d ≈ ~$150–$300/mo

**Total estimated (storage+compute): ~$850 – $1,300/mo**. Well under **$5,000/tháng** (buffer ~3.7K). Math is conservative (uses hot for 7d only, cold for year aggregates).

> Note: numbers are illustrative for the architecture decision; not production-verified. Assumptions documented.

## 6. MVP Slice (1-week build plan) + Acceptance Criteria

**Goal:** smallest shippable slice chứng minh architecture works, focus on *hardest mechanism* (PII tokenization gate + lifecycle + hot-path query).

### Week Slice (priority order)

**Day 1–2 (Bronze Gate + PII tokenization) – HARDEST**
- Implement Bronze landing (immutable) + deterministic PII tokenizer (emails, phones, IDs, common patterns). Enforce forbidden columns in Silver/Gold contracts.
- **Acceptance:** PII scan returns 0 hits on Silver sample (1000 random rows). Audit log written on every tokenize action. Schema enforcement blocks bad write.

**Day 3 (Silver normalization + dedup + Z-order)**
- Bronze→Silver: dedup by (request_id, ts), normalize, tenant enrichment. Apply Z-order (tenant, route). Compaction to target 128MB.
- **Acceptance:** Dedup removes seeded duplicates (like NB4). File count reduced ≥10× after OPTIMIZE (mechanism from NB2). Query filter by tenant scans < 20% of files vs unoptimized.

**Day 4 (Gold aggregates + 5-min refresh path)**
- Silver→Gold hourly/daily aggregates (cost, latency p95, tokens by tenant/model). Partition by agg_date. Iceberg metadata structure.
- **Acceptance:** Dashboard query (tenant filter + last 24h) returns < 500ms p95 on test corpus. Row count consistent (reproducible).

**Day 5 (Lifecycle + retention)**
- Implement lifecycle rules: delete full-trace fields >7d (soft/physical per policy), Gold retain 1y. Verify time-travel window behavior.
- **Acceptance:** After simulated +7d marker, full prompt/response not readable via normal path; aggregates still accessible. Time-travel only exposes full traces within ≤7d window (policy enforced).

**Day 6 (Lineage + Audit + Failure drills)**
- OpenLineage events Bronze→Silver→Gold. Audit table for PII-access. Run FM-1 (tokenizer bug) + FM-2 (small files) drills.
- **Acceptance:** Audit shows who/when/why for any access. FM-1 drill succeeds: quarantine→RESTORE→reprocess passes contract. FM-2: files_pruned ≥5× after compaction.

**Day 7 (Cost check + harden)**
- Measure storage size vs math (§5), file counts, scan bytes. Tweak compaction cadence.
- **Acceptance:** Measured storage (simulated 7-day window) within ±20% of back-of-envelope, total projected < $5K/mo.

### Hardest mechanism to validate
**PII tokenization at Bronze gate (shift-left)** – hardest because: (1) false negatives (miss PII) = compliance risk, (2) false positives break usability, (3) must be deterministic for replay/reprocessing (token ↔ context consistency), (4) must run before any downstream write/share. This is validated via contract tests + regex sampling + full-table scan in non-prod.

### PoC (optional but recommended)
`submission/bonus/poc/tokenization_gate_poc.py` (50–150 lines): demo deterministic tokenization + forbidden-columns contract + idempotent reprocessing (Bronze→Silver with MERGE). Proves the hardest part feasible without full infra.

## References (concepts Day18 applied)
- Medallion: Bronze/Silver/Gold separation with clear responsibilities
- ACID: MERGE, OPTIMIZE/rewrite, RESTORE (time travel)
- Time Travel: incident replay, last-known-good restore (≤7d full traces)
- Catalogs: Iceberg REST Catalog (vendor-neutral)
- Lineage: OpenLineage + audit trail
- Security/Governance: PII shift-left, RBAC, contracts
- FinOps: tiering, lifecycle, cost math with back-of-envelope
- Performance: Z-order/clustering, compaction cadence, file-sizing
