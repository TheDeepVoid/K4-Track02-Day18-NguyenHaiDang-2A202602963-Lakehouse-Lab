# Student Information

- **Full Name:** Nguyễn Hải Đăng
- **Student ID (MSSV):** 2A202602963
- **Course:** K4-Track02-Day18 - Lakehouse Lab
- **Repository:** K4-Track02-Day18-NguyenHaiDang-2A202602963-Lakehouse-Lab

## Lab Execution Summary

All required steps completed successfully (lightweight path):

1. ✅ `make setup` / manual: created venv, installed deps, generated notebooks from Jupytext
2. ✅ `make smoke` / `python scripts/verify_lite.py` - all 9 offline checks passed
3. ✅ `make data` / `python scripts/generate_data_lite.py` - generated 200,000 Bronze rows
4. ✅ `make data-ai` / `python scripts/generate_ai_data.py` - generated multimodal corpus, blobs, traces
5. ✅ `make test` / `pytest -q` - all 24 pytest tests passed
6. ✅ `make run-all` / `python scripts/run_all.py` - all 8 notebooks passed (8/8)

## Execution Environment

- **OS:** Linux (workspace)
- **Python:** 3.11 (in local `.venv/`)
- **Path:** Lightweight (delta-rs 1.x, pyiceberg, DuckDB, Polars; offline, no JVM)
- **Notebooks:** 8 lightweight notebooks executed with outputs preserved in `submission/notebooks/`
