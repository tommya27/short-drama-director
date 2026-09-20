# Short Drama Director backend

Run from the new project root after installing `requirements.txt`:

```powershell
python -m uvicorn api.app:app --app-dir . --host 127.0.0.1 --port 8200
```

Alternative equivalent entry point: `backend.main:app`.

The standalone package lives in `backend/director_core`; it has no runtime import
from `baytech2026` or its legacy API. Tests are under `backend/tests`.

```powershell
python -m pytest backend/tests -q
```

For the local Python 3.13 dependency cache used during this session:

```powershell
$env:PYTHONPATH = ((Get-Location).Path + ';' + (Join-Path (Get-Location) 'backend') + ';' + (Join-Path (Get-Location) 'backend/.depsclean'))
py -3.13 -m pytest backend/tests -q
```
