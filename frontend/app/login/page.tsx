import { Suspense } from "react";
import { LuFlaskConical, LuListChecks, LuShieldCheck } from "react-icons/lu";
import LoginForm from "@/components/LoginForm";
import Logo from "@/components/Logo";
import { cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

export const metadata = { title: "Sign in · AutoML Lab" };

const FEATURES = [
  {
    icon: LuListChecks,
    title: "Validate your data",
    text: "Upload a CSV and see its schema and data-quality warnings.",
  },
  {
    icon: LuFlaskConical,
    title: "Compare models fairly",
    text: "Allowlisted scikit-learn models, ranked on a held-out test set.",
  },
  {
    icon: LuShieldCheck,
    title: "Approve before serving",
    text: "A model answers predictions only after you approve it.",
  },
];

export default function LoginPage() {
  return (
    <main
      id="main"
      className="mx-auto grid w-full max-w-7xl flex-1 grid-cols-1 items-center gap-12 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:gap-20 lg:px-8 lg:py-20"
    >
      <section aria-label="About AutoML Lab" className="hidden flex-col gap-10 lg:flex">
        <Logo eager className="h-12 self-start" />
        <p className="max-w-lg text-5xl leading-[1.05] font-semibold tracking-tight">
          Automated machine learning for <span className="text-accent">tabular data.</span>
        </p>
        <ul className="flex max-w-md flex-col gap-5">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title} className="flex gap-4">
              <span
                aria-hidden="true"
                className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-bg text-text shadow-xs"
              >
                <Icon className="size-5" />
              </span>
              <div>
                <p className="font-medium">{title}</p>
                <p className="text-sm text-muted">{text}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className={cn(cardClass, "mx-auto flex w-full max-w-md flex-col gap-8 p-8 sm:p-10")}>
        <Logo eager className="h-10 self-start lg:hidden" />
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">Sign in</h1>
          <p className="text-muted">Use your Google account to sign in securely.</p>
        </div>
        <Suspense fallback={<p className="text-muted">Loading…</p>}>
          <LoginForm />
        </Suspense>
        <p className="border-t border-border/60 pt-6 text-xs leading-5 text-muted">
          Your session belongs to this tab only and ends when you sign out or it expires.
        </p>
      </div>
    </main>
  );
}
