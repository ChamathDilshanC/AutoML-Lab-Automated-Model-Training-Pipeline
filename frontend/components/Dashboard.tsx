"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { IconType } from "react-icons";
import {
  LuArrowRight,
  LuArrowUpRight,
  LuBookOpen,
  LuBoxes,
  LuCircleCheck,
  LuClock,
  LuCloudUpload,
  LuFlaskConical,
  LuListChecks,
  LuShieldCheck,
  LuSparkles,
} from "react-icons/lu";
import { useAuth } from "@/components/AuthProvider";
import HealthStatus from "@/components/HealthStatus";
import Logo from "@/components/Logo";
import { Eyebrow } from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { AnimateCount } from "@/components/unlumen-ui/animate-count";
import { AnimatedList } from "@/components/unlumen-ui/animated-list";
import { HoverFeatureCards } from "@/components/unlumen-ui/hover-feature-cards";
import { MotionAccordion } from "@/components/unlumen-ui/motion-faqs-accordion";
import { TiltCard } from "@/components/unlumen-ui/tilt-card";
import { errorMessage, listModels } from "@/lib/api";
import { algorithmLabel } from "@/lib/format";
import { notifyError } from "@/lib/notifications";
import type { RegisteredModel } from "@/lib/types";
import { buttonClass, cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

const DOCS_URL =
  "https://github.com/ChamathDilshanC/AutoML-Lab-Automated-Model-Training-Pipeline/blob/main/docs/README.md";

function StepVisual({ icon: Icon, chips }: { icon: IconType; chips: string[] }) {
  return (
    <div className="relative flex w-full flex-col items-center gap-4">
      <div
        aria-hidden="true"
        className="absolute inset-x-2 top-8 h-px bg-gradient-to-r from-transparent via-border to-transparent"
      />
      <span className="relative flex size-16 items-center justify-center rounded-2xl border border-border/70 bg-bg text-text shadow-sm">
        <Icon aria-hidden="true" className="size-7" />
      </span>
      <div className="flex flex-wrap justify-center gap-1.5">
        {chips.map((chip) => (
          <span
            key={chip}
            className="rounded-full border border-border/70 bg-bg px-2.5 py-0.5 text-xs font-medium text-muted"
          >
            {chip}
          </span>
        ))}
      </div>
    </div>
  );
}

const STEPS = [
  {
    eyebrow: "Step 1",
    name: "Upload a CSV",
    description: "Drag in a tabular CSV. It is stored privately and checked straight away.",
    visual: <StepVisual icon={LuCloudUpload} chips={["data.csv", "Private"]} />,
  },
  {
    eyebrow: "Step 2",
    name: "Check data quality",
    description: "See every column's type, missing values and distinct values, with warnings.",
    visual: <StepVisual icon={LuListChecks} chips={["Schema", "Warnings"]} />,
  },
  {
    eyebrow: "Step 3",
    name: "Train and compare",
    description:
      "Pick a target and metric. A worker tunes each algorithm and ranks them on a held-out test set.",
    visual: <StepVisual icon={LuFlaskConical} chips={["Cross-validation", "Leaderboard"]} />,
  },
  {
    eyebrow: "Step 4",
    name: "Approve and predict",
    description: "The best model is registered. Approve it, then try predictions from its page.",
    visual: <StepVisual icon={LuShieldCheck} chips={["Versioned", "Approval"]} />,
  },
];

const FAQS = [
  {
    question: "How is the best model chosen?",
    answer:
      "Each algorithm you select is trained on the training rows, with its parameters tuned by cross-validation on those rows only. Every candidate is then scored once on the held-out test set, and the best score on your chosen metric wins. Ties are broken by algorithm name.",
  },
  {
    question: "Is the target column ever used as an input?",
    answer:
      "No. The target is never a feature, and imputers, encoders and scalers are fitted on the training rows only, so nothing leaks from the test set.",
  },
  {
    question: "Why does a model need approval?",
    answer:
      "A registered model cannot answer prediction requests until you approve it. Revoking an approval is permanent: run a new experiment to get a new version.",
  },
  {
    question: "Can I reproduce a result?",
    answer:
      "Yes. Every experiment records its random seed, split strategy and library versions. You can find them under “How this was evaluated” on the experiment's page.",
  },
  {
    question: "What does deleting a dataset remove?",
    answer:
      "Everything made from it: its experiments, their results and its models, including approved ones, together with all stored files. It cannot be undone.",
  },
];

/** Bottom row of a quick-action card, pinned to the card's lower edge. */
function TiltFooter({ icon: Icon, label }: { icon: IconType; label: string }) {
  return (
    <span className="absolute inset-x-4 bottom-4 flex items-end justify-between sm:inset-x-6 sm:bottom-5">
      <span
        aria-hidden="true"
        className="flex size-12 items-center justify-center rounded-2xl border border-border/70 bg-surface text-text"
      >
        <Icon className="size-6" />
      </span>
      <span className="inline-flex items-center gap-1 text-sm font-medium">
        {label}
        <LuArrowUpRight aria-hidden="true" className="size-4" />
      </span>
    </span>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number | null;
  icon: IconType;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border/60 bg-surface/60 p-4">
      <dt className="flex items-center gap-1.5 text-xs font-medium text-muted">
        <Icon aria-hidden="true" className="size-3.5" />
        {label}
      </dt>
      <dd className="text-3xl font-semibold tracking-tight">
        {value === null ? "–" : <AnimateCount className="justify-items-start">{value}</AnimateCount>}
      </dd>
    </div>
  );
}

export default function Dashboard() {
  const { auth } = useAuth();
  const [models, setModels] = useState<RegisteredModel[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    listModels(controller.signal)
      .then(setModels)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setLoadFailed(true);
        notifyError("Could not load your models", errorMessage(err));
      });
    return () => controller.abort();
  }, []);

  const who = auth.status === "authenticated" ? (auth.email ?? auth.username) : "";
  const count = (status?: RegisteredModel["approval_status"]) =>
    loadFailed
      ? null
      : (models ?? []).filter((model) => !status || model.approval_status === status).length;
  const recent = (models ?? []).slice(0, 3).map((model) => ({ id: model.model_id, model }));

  return (
    <>
      <section className="grid grid-cols-1 items-center gap-10 lg:grid-cols-12 lg:gap-12">
        <div className="flex flex-col gap-6 lg:col-span-7">
          <Eyebrow icon={LuSparkles}>Automated model intelligence</Eyebrow>
          <h1 className="text-4xl leading-[1.05] font-semibold tracking-tight sm:text-5xl lg:text-6xl">
            Train better models, <span className="text-accent">faster.</span>
          </h1>
          <p className="max-w-xl text-lg leading-8 text-muted">
            Upload a tabular CSV and choose what to predict. AutoML Lab trains, tunes and ranks
            allowlisted scikit-learn models, then serves the winner once you approve it.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/datasets/new" className={buttonClass("primary", "lg")}>
              <LuCloudUpload aria-hidden="true" className="size-5" />
              Upload a dataset
            </Link>
            <Link href="/models" className={buttonClass("secondary", "lg")}>
              Browse models
              <LuArrowRight aria-hidden="true" className="size-4" />
            </Link>
          </div>
          <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted">
            {["Reproducible seeds", "Held-out test set", "Approval before predictions"].map((item) => (
              <li key={item} className="inline-flex items-center gap-2">
                <LuCircleCheck aria-hidden="true" className="size-4 text-success" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <aside aria-labelledby="workspace-title" className="lg:col-span-5">
          <div className={cn(cardClass, "flex flex-col gap-6 p-6 sm:p-7")}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-bg">
                  <Logo variant="mark" className="h-6" />
                </span>
                <div className="min-w-0">
                  <h2 id="workspace-title" className="font-semibold tracking-tight">
                    Your workspace
                  </h2>
                  <p className="truncate text-sm text-muted">{who}</p>
                </div>
              </div>
              <HealthStatus />
            </div>

            <dl className="grid grid-cols-3 gap-3">
              <Stat label="Models" value={count()} icon={LuBoxes} />
              <Stat label="Approved" value={count("APPROVED")} icon={LuShieldCheck} />
              <Stat label="Pending" value={count("PENDING")} icon={LuClock} />
            </dl>

            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Recent models</h3>
                <Link
                  href="/models"
                  className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
                >
                  View all
                  <LuArrowRight aria-hidden="true" className="size-3.5" />
                </Link>
              </div>
              {models === null && !loadFailed && (
                <p role="status" className="text-sm text-muted">
                  Loading models…
                </p>
              )}
              {loadFailed && <p className="text-sm text-muted">Models could not be loaded.</p>}
              {models?.length === 0 && (
                <p className="rounded-2xl border border-dashed border-border p-4 text-sm text-muted">
                  No models yet. A model is registered when an experiment succeeds.
                </p>
              )}
              <AnimatedList
                items={recent}
                gap={8}
                animation="slide"
                renderItem={({ model }) => (
                  <Link
                    href={`/models/${model.model_id}`}
                    className="group flex items-center gap-3 rounded-2xl border border-border/60 bg-bg p-3 transition hover:border-text/25 hover:shadow-sm"
                  >
                    <span
                      aria-hidden="true"
                      className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-surface text-text/70"
                    >
                      <LuBoxes className="size-4" />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm font-medium">
                        {model.dataset_filename ?? "Model"} → {model.target_column}
                      </span>
                      <span className="truncate text-xs text-muted">
                        v{model.version} · {algorithmLabel(model.algorithm)}
                      </span>
                    </span>
                    <StatusBadge status={model.approval_status} />
                  </Link>
                )}
              />
            </div>
          </div>
        </aside>
      </section>

      <section aria-labelledby="quick-title" className="flex flex-col gap-5">
        <h2 id="quick-title" className="text-2xl font-semibold tracking-tight">
          Jump back in
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <Link href="/datasets/new" className="block rounded-lg">
            <TiltCard
              title="Upload a dataset"
              description="Drop in a CSV and get its schema and data-quality report."
              price="CSV"
            >
              <TiltFooter icon={LuCloudUpload} label="Upload" />
            </TiltCard>
          </Link>
          <Link href="/models" className="block rounded-lg">
            <TiltCard
              title="Review models"
              description="Approve the best model from an experiment, or revoke one."
              price="Registry"
            >
              <TiltFooter icon={LuBoxes} label="Open models" />
            </TiltCard>
          </Link>
          <a href={DOCS_URL} target="_blank" rel="noreferrer" className="block rounded-lg">
            <TiltCard
              title="Read the documentation"
              description="How training, evaluation and the model registry work."
              price="Docs"
            >
              <TiltFooter icon={LuBookOpen} label="Read on GitHub" />
              <span className="sr-only">(opens in a new tab)</span>
            </TiltCard>
          </a>
        </div>
      </section>

      <section aria-labelledby="how-title" className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <h2 id="how-title" className="text-2xl font-semibold tracking-tight">
            How it works
          </h2>
          <p className="text-muted">From a raw CSV to an approved model in four steps.</p>
        </div>
        <HoverFeatureCards items={STEPS} className="lg:grid-cols-4" />
      </section>

      <section aria-labelledby="faq-title" className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <div className="flex flex-col gap-3 lg:col-span-4">
          <h2 id="faq-title" className="text-2xl font-semibold tracking-tight">
            Questions, answered
          </h2>
          <p className="text-muted">
            What AutoML Lab does with your data, and how it decides which model is best.
          </p>
        </div>
        <MotionAccordion items={FAQS} className="lg:col-span-8" />
      </section>
    </>
  );
}
