import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { LanguageProvider } from "@/providers/LanguageProvider";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "StudyFlow",
    template: "%s · StudyFlow",
  },
  description: "A focused workspace for learning with clarity.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem("studyflow.theme")==="dark")document.documentElement.classList.add("dark");document.documentElement.lang=localStorage.getItem("studyflow.language")==="en"?"en":"tr"}catch{}`,
          }}
        />
      </head>
      <body><LanguageProvider>{children}</LanguageProvider></body>
    </html>
  );
}
