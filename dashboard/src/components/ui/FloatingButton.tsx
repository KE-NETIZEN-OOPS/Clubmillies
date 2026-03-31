'use client';

import { motion } from 'framer-motion';
import { ReactNode } from 'react';

interface FloatingButtonProps {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}

export default function FloatingButton({ children, onClick, className = '' }: FloatingButtonProps) {
  return (
    <motion.button
      className={`fixed bottom-8 right-8 w-14 h-14 rounded-full bg-gradient-to-r from-neon-cyan to-neon-blue
        flex items-center justify-center shadow-glow-lg z-50 ${className}`}
      animate={{ y: [0, -8, 0] }}
      transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
      whileHover={{ scale: 1.1, boxShadow: '0 0 40px rgba(0, 212, 255, 0.6)' }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
    >
      {children}
    </motion.button>
  );
}
