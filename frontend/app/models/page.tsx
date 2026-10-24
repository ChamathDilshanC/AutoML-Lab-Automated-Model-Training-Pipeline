import Link from "next/link";
import ModelList from "@/components/ModelList";

export const metadata = { title: "Models · AutoML Lab" };

export default function ModelsPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-12">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link href="/" className="underline">
          Home
        </Link>{" "}
        › Models
      </nav>
      <h1 className="text-3xl font-semibold tracking-tight">Models</h1>
      <p className="text-muted">
        The best model from each successful experiment. Approve a model to let it make predictions.
      </p>
      <ModelList />
    </main>
  );
}
