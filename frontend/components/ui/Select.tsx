import { LuChevronDown } from "react-icons/lu";
import { fieldClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

/** A native select with a custom chevron. */
export default function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select {...props} className={cn(fieldClass, "cursor-pointer appearance-none pr-10", className)} />
      <LuChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-3.5 size-4 -translate-y-1/2 text-muted"
      />
    </div>
  );
}
