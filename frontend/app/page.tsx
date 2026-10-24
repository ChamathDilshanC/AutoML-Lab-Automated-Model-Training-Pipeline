import Link from "next/link";
import HealthStatus from "@/components/HealthStatus";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">AutoML Lab</h1>
      <p className="text-lg text-muted">
        Automated model training, evaluation and inference for tabular CSV data.
      </p>
      <div>
        <Link
          href="/datasets/new"
          className="inline-block rounded-md bg-accent px-4 py-2 font-medium text-on-accent"
        >
          Upload a dataset
        </Link>
      </div>
      <HealthStatus />
    </main>
  );
}
