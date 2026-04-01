// app/layout.tsx
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: '🇨🇱 IPSA Agent — Dashboard',
  description: 'Gestor Autónomo de Inversión IPSA Chile',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className={inter.className} style={{ backgroundColor: '#0a0e1a', color: '#e2e8f0' }}>
        {children}
      </body>
    </html>
  );
}
