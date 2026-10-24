import AppHeader from "@/components/AppHeader";
import AuthGate from "@/components/AuthGate";

// Everything in this route group needs a signed-in user. /login is outside it.
//
// The gate renders its children only once the browser's token has been checked, so these pages
// are client-rendered by design and cannot be part of a static shell. Opting out tells Next.js's
// development-time instant-navigation validation not to expect otherwise.
export const instant = false;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <AppHeader />
      <AuthGate>{children}</AuthGate>
    </>
  );
}
