import { Suspense } from "react";
import ExperimentDetail from "@/components/ExperimentDetail";
import { Breadcrumbs, PageMain } from "@/components/PageHeader";
import { LoadingState } from "@/components/ui/States";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "Experiment · AutoML Lab" };

async function ExperimentView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ExperimentDetail experimentId={id} />;
}

export default function ExperimentPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <PageMain className="gap-8">
      <Breadcrumbs items={[{ label: "Experiment" }]} />
      <Suspense fallback={<LoadingState label="Loading experiment…" />}>
        <ExperimentView params={params} />
      </Suspense>
    </PageMain>
  );
}
