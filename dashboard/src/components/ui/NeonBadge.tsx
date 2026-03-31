'use client';

interface NeonBadgeProps {
  label: string;
  variant?: 'buy' | 'sell' | 'sniper' | 'aggressive' | 'profit' | 'loss' | 'neutral';
  size?: 'sm' | 'md';
}

const VARIANTS = {
  buy: 'bg-profit/20 text-profit border-profit/30 shadow-glow-profit',
  sell: 'bg-loss/20 text-loss border-loss/30 shadow-glow-loss',
  sniper: 'bg-neon-cyan/20 text-neon-cyan border-neon-cyan/30 shadow-glow',
  aggressive: 'bg-gold/20 text-gold border-gold/30 shadow-glow-gold',
  profit: 'bg-profit/20 text-profit border-profit/30',
  loss: 'bg-loss/20 text-loss border-loss/30',
  neutral: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

export default function NeonBadge({ label, variant = 'neutral', size = 'sm' }: NeonBadgeProps) {
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';
  return (
    <span className={`inline-flex items-center rounded-full border font-medium ${sizeClass} ${VARIANTS[variant]}`}>
      {label}
    </span>
  );
}
