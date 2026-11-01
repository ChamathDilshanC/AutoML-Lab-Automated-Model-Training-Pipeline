import { Suspense } from "react";
import { LuFlaskConical } from "react-icons/lu";
import ExperimentForm from "@/components/ExperimentForm";
import PageHeader, { Breadcrumbs, PageMain } from "@/components/PageHeader";
import { LoadingState } from "@/components/ui/States";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "New experiment · AutoML Lab" };

export default function NewExperimentPage() {
  return (
    <PageMain>
      <div className="flex flex-col gap-6">
        <Breadcrumbs items={[{ label: "New experiment" }]} />
        <PageHeader
          eyebrow="Step 3 of 4"
          eyebrowIcon={LuFlaskConical}
          title="New experiment"
          description="Choose what to predict and which algorithms to compare. A separate worker trains them and the results appear on the next page."
        />
      </div>
      <Suspense fallback={<LoadingState label="Loading…" />}>
        <ExperimentForm />
      </Suspense>
    </PageMain>
  );
}
