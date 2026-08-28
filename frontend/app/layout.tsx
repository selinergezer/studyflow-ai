import type { Metadata } from "next";
import { Bricolage_Grotesque, Inter, Kalam, Space_Mono } from "next/font/google";
import { LanguageProvider } from "@/providers/LanguageProvider";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const bricolage = Bricolage_Grotesque({ variable: "--font-bricolage", subsets: ["latin"], display: "swap" });
const kalam = Kalam({ variable: "--font-kalam", subsets: ["latin"], weight: ["400", "700"], display: "swap" });
const spaceMono = Space_Mono({ variable: "--font-space-mono", subsets: ["latin"], weight: ["400", "700"], display: "swap" });

export const metadata: Metadata = {
  title: {
    default: "StudyFlow",
    template: "%s · StudyFlow",
  },
  description: "A focused workspace for learning with clarity.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${bricolage.variable} ${kalam.variable} ${spaceMono.variable}`} suppressHydrationWarning>
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
