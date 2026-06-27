import * as React from "react";

import { cn } from "@/lib/utils";

function Card({ className, glass = false, ...props }: React.ComponentProps<"div"> & { glass?: boolean }) {
  return (
    <div
      data-slot="card"
      data-glass={glass || undefined}
      className={cn(
        "rounded-xl border border-line bg-surface text-ink shadow-card transition-shadow duration-200",
        glass && "glass-panel",
        className
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-header" className={cn("flex flex-col gap-1.5 px-5 pt-5", className)} {...props} />;
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-title" className={cn("font-semibold leading-none text-ink", className)} {...props} />;
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-description" className={cn("text-sm text-ink-muted", className)} {...props} />;
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("px-5 py-5", className)} {...props} />;
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-footer" className={cn("flex items-center px-5 pb-5", className)} {...props} />;
}

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter };
