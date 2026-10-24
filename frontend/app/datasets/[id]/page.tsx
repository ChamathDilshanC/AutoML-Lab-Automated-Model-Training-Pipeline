import Link from "next/link";
import { Suspense } from "react";
import DatasetDetail from "@/components/DatasetDetail";

export const metadata = { title: "Dataset · AutoML Lab" };

async function DatasetView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DatasetDetail datasetId={id} />;
}

export default function DatasetPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-12">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link href="/" className="underline">
          Home
        </Link>{" "}
        ›{" "}
        <Link href="/datasets/new" className="underline">
          Upload dataset
        </Link>{" "}
        › Dataset
      </nav>
      <Suspense fallback={<p className="text-muted">Loading dataset…</p>}>
        <DatasetView params={params} />
      </Suspense>
    </main>
  );
}
