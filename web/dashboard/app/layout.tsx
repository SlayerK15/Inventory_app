import "./globals.css";
import { ReactNode } from "react";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 font-sans">
        <div className="max-w-6xl mx-auto py-12 px-6">{children}</div>
      </body>
    </html>
  );
}
