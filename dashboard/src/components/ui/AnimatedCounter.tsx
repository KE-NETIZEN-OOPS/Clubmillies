'use client';

import { useEffect, useState } from 'react';
import { motion, useSpring, useTransform } from 'framer-motion';

interface AnimatedCounterProps {
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  className?: string;
  duration?: number;
}

export default function AnimatedCounter({
  value, prefix = '', suffix = '', decimals = 2, className = '', duration = 1,
}: AnimatedCounterProps) {
  const spring = useSpring(0, { duration: duration * 1000 });
  const display = useTransform(spring, (v) =>
    `${prefix}${v.toFixed(decimals)}${suffix}`
  );
  const [displayValue, setDisplayValue] = useState(`${prefix}0${suffix}`);

  useEffect(() => {
    spring.set(value);
    const unsub = display.on('change', (v) => setDisplayValue(v));
    return () => unsub();
  }, [value, spring, display]);

  return (
    <motion.span className={className}>
      {displayValue}
    </motion.span>
  );
}
