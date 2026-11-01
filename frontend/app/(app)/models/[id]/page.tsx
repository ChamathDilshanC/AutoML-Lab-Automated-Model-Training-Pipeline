import { Suspense } from "react";
import ModelDetail from "@/components/ModelDetail";
import { Breadcrumbs, PageMain } from "@/components/PageHeader";
import { LoadingState } from "@/components/ui/States";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "Model · AutoML Lab" };

async function ModelView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ModelDetail modelId={id} />;
}

export default function ModelPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <PageMain className="gap-8">
      <Breadcrumbs items={[{ label: "Models", href: "/models" }, { label: "Model" }]} />
      <Suspense fallback={<LoadingState label="Loading model…" />}>
        <ModelView params={params} />
      </Suspense>
    </PageMain>
  );
}
