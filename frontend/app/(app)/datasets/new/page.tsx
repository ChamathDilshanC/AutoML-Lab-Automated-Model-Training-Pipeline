import { LuCircleCheck, LuFlaskConical, LuListChecks, LuTable2 } from "react-icons/lu";
import DatasetUploader from "@/components/DatasetUploader";
import PageHeader, { Breadcrumbs, PageMain } from "@/components/PageHeader";
import { cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export const metadata = { title: "Upload dataset · AutoML Lab" };

const CHECKLIST = [
  "A .csv file with column names in the first row",
  "One row per example, including the column you want to predict",
  "Up to 10 MB with the server's default limit",
];

const NEXT_STEPS = [
  { icon: LuListChecks, title: "Validation", text: "Rows, columns and types are checked." },
  { icon: LuTable2, title: "Schema and warnings", text: "Review missing values and data-quality notes." },
  { icon: LuFlaskConical, title: "Experiment", text: "Choose a target and compare algorithms." },
];

export default function NewDatasetPage() {
  return (
    <PageMain>
      <div className="flex flex-col gap-6">
        <Breadcrumbs items={[{ label: "Upload dataset" }]} />
        <PageHeader
          eyebrow="Step 1 of 4"
          title="Upload a dataset"
          description="Upload a CSV file. It is validated and you will see its schema and any data-quality warnings."
        />
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <DatasetUploader />
        </div>

        <aside className="flex flex-col gap-4 lg:col-span-4">
          <section aria-labelledby="checklist-title" className={cn(cardClass, "rounded-2xl p-6")}>
            <h2 id="checklist-title" className="font-semibold tracking-tight">
              Before you upload
            </h2>
            <ul className="mt-4 flex flex-col gap-3 text-sm text-muted">
              {CHECKLIST.map((item) => (
                <li key={item} className="flex gap-2.5">
                  <LuCircleCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="next-title" className={cn(cardClass, "rounded-2xl p-6")}>
            <h2 id="next-title" className="font-semibold tracking-tight">
              What happens next
            </h2>
            <ol className="mt-4 flex flex-col gap-4">
              {NEXT_STEPS.map(({ icon: Icon, title, text }, index) => (
                <li key={title} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-surface text-text/70"
                  >
                    <Icon className="size-4" />
                  </span>
                  <div className="text-sm">
                    <p className="font-medium">
                      <span className="sr-only">Step {index + 1}: </span>
                      {title}
                    </p>
                    <p className="text-muted">{text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </PageMain>
  );
}
