import type { Metadata } from 'next';
import { Figtree, Lora } from 'next/font/google';
import './globals.css';

// Humanist sans: body text, labels, UI
const figtree = Figtree({
  subsets: ['latin'],
  variable: '--font-figtree',
  display: 'swap',
  weight: ['400', '500', '600'],
});

// Serif: display numbers, section headings
const lora = Lora({
  subsets: ['latin'],
  variable: '--font-lora',
  display: 'swap',
  weight: ['400', '600'],
  style: ['normal'],
});

export const metadata: Metadata = {
  title: 'CivicFlow - Honolulu Permit Advisor',
  description:
    'Predict DPP processing time and verify submittal requirements before you file.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${figtree.variable} ${lora.variable}`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
