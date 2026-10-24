# AutoML Lab frontend

Next.js (App Router, TypeScript, Tailwind CSS) shell for AutoML Lab. See the [documentation index](../docs/README.md) and the [design system](../docs/DESIGN_SYSTEM.md).

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run typecheck
npm run build
```

The backend URL is read from `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`). See `.env.example` at the repository root.
