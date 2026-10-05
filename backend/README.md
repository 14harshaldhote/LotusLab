# LotusLab backend

FastAPI service and pure-Python simulation core. See the [project README](../README.md).

```bash
pip install -e ".[dev]"
uvicorn lotuslab.main:app --reload     # http://127.0.0.1:8000/docs
pytest
python -m benchmarks.bench
```
