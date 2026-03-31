'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import FloatingButton from '@/components/ui/FloatingButton';
import { api, AccountData } from '@/lib/api';

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<AccountData[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    name: '', broker_type: 'paper', profile: 'SNIPER',
    symbol: 'XAUUSD.s', balance: 10000, risk_per_trade: 0.02,
    login: '', password: '', server: '',
  });

  useEffect(() => { loadAccounts(); }, []);

  async function loadAccounts() {
    try { setAccounts(await api.accounts()); } catch (e) { console.error(e); }
  }

  async function createAccount() {
    try {
      await api.createAccount(form);
      setShowModal(false);
      loadAccounts();
    } catch (e) { console.error(e); }
  }

  async function toggleAccount(id: number) {
    try { await api.toggleAccount(id); loadAccounts(); } catch (e) { console.error(e); }
  }

  async function deleteAccount(id: number) {
    if (!confirm('Delete this account?')) return;
    try { await api.deleteAccount(id); loadAccounts(); } catch (e) { console.error(e); }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Accounts</h1>
        <motion.button
          className="px-4 py-2 bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30 rounded-xl hover:shadow-glow transition-all"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => setShowModal(true)}
        >
          + Add Account
        </motion.button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {accounts.map((acc) => (
          <GlowCard key={acc.id} animate>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${acc.enabled ? 'bg-profit pulse-dot pulse-dot-green' : 'bg-gray-600'}`} />
                <h3 className="font-bold text-lg">{acc.name}</h3>
              </div>
              <NeonBadge label={acc.profile} variant={acc.profile === 'SNIPER' ? 'sniper' : 'aggressive'} />
            </div>

            <div className="space-y-2 mb-4">
              <div className="flex justify-between"><span className="text-gray-500">Balance</span><span className="font-mono text-lg">${acc.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Equity</span><span className="font-mono">${acc.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Broker</span><span className="text-gray-300">{acc.broker_type.toUpperCase()}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Symbol</span><span className="text-gold">{acc.symbol}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Risk</span><span>{(acc.risk_per_trade * 100).toFixed(0)}%</span></div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => toggleAccount(acc.id)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
                  acc.enabled ? 'bg-loss/20 text-loss hover:bg-loss/30' : 'bg-profit/20 text-profit hover:bg-profit/30'
                }`}
              >
                {acc.enabled ? 'Pause' : 'Resume'}
              </button>
              <button
                onClick={() => deleteAccount(acc.id)}
                className="px-3 py-2 rounded-lg text-sm text-gray-500 hover:text-loss hover:bg-loss/10 transition-all"
              >
                Delete
              </button>
            </div>
          </GlowCard>
        ))}
      </div>

      {/* Add Account Modal */}
      <AnimatePresence>
        {showModal && (
          <motion.div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowModal(false)}
          >
            <motion.div
              className="glow-card p-8 w-full max-w-md"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-xl font-bold mb-6">Add Account</h2>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-500 block mb-1">Name</label>
                  <input className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white focus:border-neon-cyan/50 outline-none" value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} placeholder="My Gold Account" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Broker</label>
                    <select className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white outline-none" value={form.broker_type} onChange={(e) => setForm({...form, broker_type: e.target.value})}>
                      <option value="paper">Paper</option>
                      <option value="mt5">MetaTrader 5</option>
                      <option value="oanda">OANDA</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Profile</label>
                    <select className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white outline-none" value={form.profile} onChange={(e) => setForm({...form, profile: e.target.value})}>
                      <option value="SNIPER">Sniper (~85% WR)</option>
                      <option value="AGGRESSIVE">Aggressive (~83% WR)</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Starting Balance</label>
                    <input type="number" className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white outline-none" value={form.balance} onChange={(e) => setForm({...form, balance: Number(e.target.value)})} />
                  </div>
                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Risk %</label>
                    <input type="number" step="0.01" className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white outline-none" value={form.risk_per_trade} onChange={(e) => setForm({...form, risk_per_trade: Number(e.target.value)})} />
                  </div>
                </div>
                {form.broker_type === 'mt5' && (
                  <div className="space-y-3 border-t border-white/10 pt-3">
                    <p className="text-xs text-gold">MT5 Credentials (JustMarkets)</p>
                    <input className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white outline-none" placeholder="Login (account number)" value={form.login} onChange={(e) => setForm({...form, login: e.target.value})} />
                    <input type="password" className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white outline-none" placeholder="Password" value={form.password} onChange={(e) => setForm({...form, password: e.target.value})} />
                    <input className="w-full bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-white outline-none" placeholder="Server (e.g. JustMarkets-Demo)" value={form.server} onChange={(e) => setForm({...form, server: e.target.value})} />
                  </div>
                )}
                <div className="flex gap-3 pt-2">
                  <button onClick={() => setShowModal(false)} className="flex-1 py-2 rounded-lg border border-white/10 text-gray-400 hover:text-white transition-all">Cancel</button>
                  <motion.button onClick={createAccount} className="flex-1 py-2 rounded-lg bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30 font-medium hover:shadow-glow transition-all" whileTap={{ scale: 0.98 }}>Create</motion.button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <FloatingButton onClick={() => setShowModal(true)}>
        <span className="text-2xl">+</span>
      </FloatingButton>
    </div>
  );
}
