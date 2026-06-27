import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors duration-150 [&_svg]:size-3",
  {
    variants: {
      variant: {
        neutral: "bg-slate-100 text-ink-muted",
        primary: "bg-primary-50 text-primary-700",
        success: "bg-accent-50 text-accent-700",
        warning: "bg-warning-50 text-warning-600",
        danger: "bg-danger-50 text-danger-600",
      },
    },
    defaultVariants: { variant: "neutral" },
  }
);

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant, className }))} {...props} />;
}

export { Badge, badgeVariants };
