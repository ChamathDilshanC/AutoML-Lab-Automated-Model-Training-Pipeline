import Link from "next/link";
import { Suspense } from "react";
import ExperimentForm from "@/components/ExperimentForm";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "New experiment · AutoML Lab" };

export default function NewExperimentPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-12">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link href="/" className="underline">
          Home
        </Link>{" "}
        › New experiment
      </nav>
      <h1 className="text-3xl font-semibold tracking-tight">New experiment</h1>
      <p className="text-muted">
        Choose what to predict and which algorithms to compare. A separate worker trains them and
        the results appear on the next page.
      </p>
      <Suspense fallback={<p className="text-muted">Loading…</p>}>
        <ExperimentForm />
      </Suspense>
    </main>
  );
}
