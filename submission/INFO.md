# Student Information

- **Full Name:** Nguyễn Hải Đăng
- **Student ID (MSSV):** 2A202602963
- **Course:** K4-Track02-Day18 - Lakehouse Lab
- **Repository:** K4-Track02-Day18-NguyenHaiDang-2A202602963-Lakehouse-Lab

## Lab Execution Summary

All required steps completed successfully:

1. ✅ `make setup` - Environment setup and notebook generation from Jupytext
2. ✅ `make smoke` - All 9 offline checks passed
3. ✅ `make data` - Generated 200,000 Bronze rows with seeded duplicates
4. ✅ `make data-ai` - Generated multimodal corpus, blobs, and agent traces
5. ✅ `make test` - All 24 pytest tests passed
6. ✅ `make run-all` - All 8 notebooks executed successfully (8/8 passed in ~14s)

## Execution Environment

- Platform: Linux
- Python: 3.10+ (in virtual environment)
- Data format: Delta Lake (delta-rs 1.x) + Apache Iceberg (pyiceberg) + DuckDB + Polars
- Execution path: Lightweight (offline, no JVM required)
