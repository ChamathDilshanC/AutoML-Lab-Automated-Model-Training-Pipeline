import Link from "next/link";
import DatasetUploader from "@/components/DatasetUploader";

export const metadata = { title: "Upload dataset · AutoML Lab" };

export default function NewDatasetPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-12">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link href="/" className="underline">
          Home
        </Link>{" "}
        › Upload dataset
      </nav>
      <h1 className="text-3xl font-semibold tracking-tight">Upload a dataset</h1>
      <p className="text-muted">
        Upload a CSV file. It is validated and you will see its schema and any data-quality
        warnings.
      </p>
      <DatasetUploader />
    </main>
  );
}
