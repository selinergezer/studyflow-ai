import type { ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  fullWidth?: boolean;
};

const variants: Record<ButtonVariant, string> = {
  primary: "bg-blue-600 text-white hover:bg-blue-700 focus-visible:outline-blue-600",
  secondary: "border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 focus-visible:outline-blue-600",
  ghost: "bg-transparent text-gray-600 hover:bg-gray-100 hover:text-gray-900 focus-visible:outline-gray-400",
};

export default function Button({
  variant = "primary",
  fullWidth = false,
  className = "",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 active:translate-y-px ${variants[variant]} ${fullWidth ? "w-full" : ""} ${className}`}
      {...props}
    />
  );
}
