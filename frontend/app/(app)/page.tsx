import Link from "next/link";
import HealthStatus from "@/components/HealthStatus";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center gap-6 px-4 py-16">
      <div className="max-w-2xl rounded-3xl border border-border/80 bg-bg/85 p-8 shadow-xl shadow-slate-200/40 backdrop-blur-sm sm:p-12">
      <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-accent">Automated model intelligence</p>
      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Train better models, faster.</h1>
      <p className="mt-4 text-lg leading-8 text-muted">
        Automated model training, evaluation and inference for tabular CSV data.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/datasets/new"
          className="inline-block rounded-xl bg-accent px-5 py-3 font-medium text-on-accent shadow-lg shadow-accent/20 transition hover:-translate-y-0.5"
        >
          Upload a dataset
        </Link>{" "}
        <Link href="/models" className="inline-block rounded-xl border border-border bg-bg px-5 py-3 font-medium transition hover:border-accent hover:text-accent">
          Models
        </Link>
      </div>
      <div className="mt-8 rounded-2xl border border-border/70 bg-surface/70 p-4">
        <HealthStatus />
      </div>
      </div>
    </main>
  );
}
