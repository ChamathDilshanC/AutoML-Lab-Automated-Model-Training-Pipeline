import Link from "next/link";
import { Suspense } from "react";
import ModelDetail from "@/components/ModelDetail";

export const metadata = { title: "Model · AutoML Lab" };

async function ModelView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ModelDetail modelId={id} />;
}

export default function ModelPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-12">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link href="/" className="underline">
          Home
        </Link>{" "}
        ›{" "}
        <Link href="/models" className="underline">
          Models
        </Link>{" "}
        › Model
      </nav>
      <Suspense fallback={<p className="text-muted">Loading model…</p>}>
        <ModelView params={params} />
      </Suspense>
    </main>
  );
}
