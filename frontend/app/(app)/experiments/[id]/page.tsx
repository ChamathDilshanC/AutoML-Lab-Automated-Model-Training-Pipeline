import Link from "next/link";
import { Suspense } from "react";
import ExperimentDetail from "@/components/ExperimentDetail";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "Experiment · AutoML Lab" };

async function ExperimentView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ExperimentDetail experimentId={id} />;
}

export default function ExperimentPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-12">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link href="/" className="underline">
          Home
        </Link>{" "}
        › Experiment
      </nav>
      <Suspense fallback={<p className="text-muted">Loading experiment…</p>}>
        <ExperimentView params={params} />
      </Suspense>
    </main>
  );
}
