import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold leading-none transition-colors duration-150 [&_svg]:size-3 border",
  {
    variants: {
      variant: {
        neutral: "bg-surface-low text-ink-muted border-border-subtle",
        primary: "bg-primary-50 text-primary-700 border-primary-100",
        success: "bg-success-50 text-success-600 border-success-50",
        warning: "bg-warning-50 text-warning-600 border-warning-50",
        danger: "bg-danger-50 text-danger-700 border-danger-50",
      },
    },
    defaultVariants: { variant: "neutral" },
  }
);

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant, className }))} {...props} />;
}

export { Badge, badgeVariants };
