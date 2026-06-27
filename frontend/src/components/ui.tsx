import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { Button as ShadButton } from "@/components/ui/button";
import { Badge as ShadBadge } from "@/components/ui/badge";
import { Input as ShadInput } from "@/components/ui/input";

export function Card({
  children,
  className = "",
  padded = true,
  glass = false,
  ...rest
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  glass?: boolean;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-line bg-surface shadow-card transition-shadow duration-200",
        glass && "glass-panel",
        padded && "p-5",
        className
      )}
      {...rest}
    >
      {glass ? <div className="relative z-10">{children}</div> : children}
    </div>
  );
}

// старый словарь вариантов проекта -> канонические варианты shadcn Button
const VARIANT_MAP = {
  primary: "default",
  secondary: "secondary",
  ghost: "ghost",
  danger: "destructive",
} as const;
const SIZE_MAP = { sm: "sm", md: "default", lg: "lg" } as const;

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  icon,
  ...rest
}: {
  children?: ReactNode;
  variant?: keyof typeof VARIANT_MAP;
  size?: keyof typeof SIZE_MAP;
  icon?: ReactNode;
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <ShadButton variant={VARIANT_MAP[variant]} size={SIZE_MAP[size]} className={className} {...rest}>
      {icon}
      {children}
    </ShadButton>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "primary" | "success" | "warning" | "danger";
  className?: string;
}) {
  return (
    <ShadBadge variant={tone} className={className}>
      {children}
    </ShadBadge>
  );
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="animate-fade-in-up flex flex-col items-center justify-center rounded-xl border border-dashed border-line-strong bg-white px-6 py-14 text-center">
      {icon && <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-50 text-primary-600">{icon}</div>}
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ size = 18, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      className={`animate-spin-slow ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Загрузка"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function LoadingBlock({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-ink-muted">
      <Spinner size={16} />
      {label}
    </div>
  );
}

export function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-line bg-white p-4">
      <div className="skeleton-shimmer h-10 w-10 shrink-0 rounded-full" />
      <div className="flex-1 space-y-2">
        <div className="skeleton-shimmer h-3 w-1/3 rounded" />
        <div className="skeleton-shimmer h-3 w-1/5 rounded" />
      </div>
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <ShadInput {...props} />;
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}
