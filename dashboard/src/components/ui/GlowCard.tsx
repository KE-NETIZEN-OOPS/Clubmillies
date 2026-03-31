'use client';

import { motion } from 'framer-motion';
import { ReactNode } from 'react';

interface GlowCardProps {
  children: ReactNode;
  className?: string;
  glowColor?: string;
  hover?: boolean;
  animate?: boolean;
}

export default function GlowCard({
  children, className = '', glowColor = 'rgba(0, 212, 255, 0.3)',
  hover = true, animate = false,
}: GlowCardProps) {
  return (
    <motion.div
      className={`glow-card p-6 ${className}`}
      initial={animate ? { opacity: 0, y: 20 } : undefined}
      animate={animate ? { opacity: 1, y: 0 } : undefined}
      whileHover={hover ? {
        borderColor: glowColor,
        boxShadow: `0 0 30px ${glowColor}`,
      } : undefined}
      transition={{ duration: 0.3 }}
    >
      {children}
    </motion.div>
  );
}
