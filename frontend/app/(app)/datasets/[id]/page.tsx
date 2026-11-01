import { Suspense } from "react";
import DatasetDetail from "@/components/DatasetDetail";
import { Breadcrumbs, PageMain } from "@/components/PageHeader";
import { LoadingState } from "@/components/ui/States";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "Dataset · AutoML Lab" };

async function DatasetView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DatasetDetail datasetId={id} />;
}

export default function DatasetPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <PageMain className="gap-8">
      <Breadcrumbs items={[{ label: "Upload dataset", href: "/datasets/new" }, { label: "Dataset" }]} />
      <Suspense fallback={<LoadingState label="Loading dataset…" />}>
        <DatasetView params={params} />
      </Suspense>
    </PageMain>
  );
}
