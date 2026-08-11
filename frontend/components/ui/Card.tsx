import type { HTMLAttributes } from "react";

export default function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-3xl border border-gray-200 bg-white shadow-[0_1px_2px_rgba(17,24,39,0.02),0_8px_28px_rgba(17,24,39,0.04)] ${className}`}
      {...props}
    />
  );
}
