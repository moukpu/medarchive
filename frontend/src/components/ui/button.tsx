import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-semibold transition-all duration-150 ease-out disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-white active:scale-[0.97] cursor-pointer",
  {
    variants: {
      variant: {
        default:
          "bg-brand-red text-white card-elev-1 hover:bg-brand-red-hover",
        destructive:
          "bg-danger-600 text-white card-elev-1 hover:bg-danger-700",
        outline:
          "border border-border-subtle bg-surface-white text-ink hover:bg-surface-low",
        secondary:
          "bg-brand-blue text-white card-elev-1 hover:bg-brand-blue-soft",
        ghost:
          "bg-transparent text-ink-muted hover:bg-surface-low hover:text-ink",
        link:
          "text-primary-600 underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 px-3 text-[13px]",
        lg: "h-11 px-5 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
