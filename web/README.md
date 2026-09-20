# Web frontend notes

The web app is an independent React + TypeScript + Vite frontend. It does not import the legacy platform UI.

Run:

```powershell
npm install
npm run dev
```

The default dev port is 5274. Set `VITE_API_BASE` to point at another backend; default is `http://127.0.0.1:8200/api/v1`.
