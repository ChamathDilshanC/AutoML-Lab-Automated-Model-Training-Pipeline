import Image from "next/image";
import wordmark from "@/public/assets/Logo/automl-lab-logo.png";
import mark from "@/public/assets/Logo/automl-lab-mark.png";
import { cn } from "@/lib/utils";

// Both images are cropped from public/assets/Logo/Auto ML Lab Logo.png (black on transparent).

interface Props {
  /** "wordmark" is the full logo; "mark" is the "A" alone, for tight spaces. */
  variant?: "wordmark" | "mark";
  className?: string;
  /** Load straight away instead of lazily, for a logo visible on first paint. */
  eager?: boolean;
}

export default function Logo({ variant = "wordmark", className, eager = false }: Props) {
  return (
    <Image
      src={variant === "mark" ? mark : wordmark}
      alt="AutoML Lab"
      loading={eager ? "eager" : "lazy"}
      className={cn(
        // object-contain keeps the shape if a flex parent stretches the box.
        "w-auto object-contain object-left select-none",
        variant === "mark" ? "h-8" : "h-9",
        className,
      )}
      draggable={false}
    />
  );
}
