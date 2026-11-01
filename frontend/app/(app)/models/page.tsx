import Link from "next/link";
import { LuBoxes, LuCloudUpload } from "react-icons/lu";
import ModelList from "@/components/ModelList";
import PageHeader, { Breadcrumbs, PageMain } from "@/components/PageHeader";
import { buttonClass } from "@/lib/ui";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "Models · AutoML Lab" };

export default function ModelsPage() {
  return (
    <PageMain>
      <div className="flex flex-col gap-6">
        <Breadcrumbs items={[{ label: "Models" }]} />
        <PageHeader
          eyebrow="Model registry"
          eyebrowIcon={LuBoxes}
          title="Models"
          description="The best model from each successful experiment. Approve a model to let it make predictions."
          actions={
            <Link href="/datasets/new" className={buttonClass("secondary")}>
              <LuCloudUpload aria-hidden="true" className="size-4" />
              Upload a dataset
            </Link>
          }
        />
      </div>
      <ModelList />
    </PageMain>
  );
}
