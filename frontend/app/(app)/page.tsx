import Dashboard from "@/components/Dashboard";
import { PageMain } from "@/components/PageHeader";

// Rendered behind the sign-in gate (see layout.tsx), so it is client-rendered by design.
export const instant = false;

export default function Home() {
  return (
    <PageMain className="gap-16 lg:gap-20">
      <Dashboard />
    </PageMain>
  );
}
