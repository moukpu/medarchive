import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors duration-150 [&_svg]:size-3 ring-1",
  {
    variants: {
      variant: {
        neutral: "bg-white/[0.07] text-ink-muted ring-white/10",
        primary: "bg-primary-500/15 text-primary-300 ring-primary-500/25",
        success: "bg-accent-500/15 text-accent-500 ring-accent-500/25",
        warning: "bg-warning-50 text-warning-500 ring-warning-500/25",
        danger: "bg-danger-50 text-danger-500 ring-danger-500/25",
      },
    },
    defaultVariants: { variant: "neutral" },
  }
);

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant, className }))} {...props} />;
}

export { Badge, badgeVariants };
