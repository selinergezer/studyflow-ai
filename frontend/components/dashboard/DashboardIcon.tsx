export type DashboardIconName = "upload" | "quiz" | "cards" | "chat" | "book";

export default function DashboardIcon({ name, className = "size-5" }: { name: DashboardIconName; className?: string }) {
  const paths: Record<DashboardIconName, React.ReactNode> = {
    upload: <path d="M12 15V4m0 0L8 8m4-4 4 4M5 14v5h14v-5" />,
    quiz: <path d="M9.5 9a2.5 2.5 0 1 1 3.8 2.15c-.8.5-1.3.9-1.3 1.85m0 3.25h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" />,
    cards: <path d="m7 6 10-2 2.5 13L9 19 7 6Zm0 2H4.5v12H15v-1.5" />,
    chat: <path d="M20 15a2 2 0 0 1-2 2H9l-5 3V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9ZM8 9h8m-8 4h5" />,
    book: <path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v12.5H7.5A2.5 2.5 0 0 1 5 17V4.5ZM5 17a2.5 2.5 0 0 1 2.5-2.5H18" />,
  };

  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
