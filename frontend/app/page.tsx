import HealthStatus from "@/components/HealthStatus";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">AutoML Lab</h1>
      <p className="text-lg text-zinc-600 dark:text-zinc-400">
        Automated model training, evaluation and inference for tabular CSV
        data.
      </p>
      <HealthStatus />
    </main>
  );
}
