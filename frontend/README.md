# AutoML Lab frontend

Next.js (App Router, TypeScript, Tailwind CSS) shell for AutoML Lab. See the [documentation index](../docs/README.md) and the [design system](../docs/DESIGN_SYSTEM.md).

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run typecheck
npm run build
```

The backend URL is read from `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`). See `.env.example` at the repository root. It is inlined into the browser bundle at build time, so a change needs a new build.

Google sign-in also requires `NEXT_PUBLIC_SUPABASE_URL`. The API must be configured with the
matching Supabase issuer and JWT verification secret/JWKS; the browser never stores the Supabase
access token.

The deployed frontend, https://automl-lab-ui.vercel.app, is built by Vercel with `NEXT_PUBLIC_API_BASE_URL` set in the Vercel project's environment variables to the API's Lambda Function URL, https://qr2bs6hofh2mxilfqoz5uk2f5i0janut.lambda-url.us-east-1.on.aws (`terraform output api_url`). The URL is not in the code.
