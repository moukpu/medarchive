import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full rounded-lg border border-line bg-surface px-3.5 text-sm text-ink outline-none transition-shadow duration-150 placeholder:text-ink-faint focus:border-primary-500 focus:ring-2 focus:ring-primary-500/25 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}

export { Input };
