import React, { useEffect, useState } from 'react';
import { 
  LayoutDashboard, 
  PlusCircle, 
  History, 
  Settings, 
  X
} from 'lucide-react';
import { LogoIcon } from './Logo';
import { fetchAudit } from '../services/api';

interface SidebarProps {
  currentRoute: string;
  navigate: (route: string) => void;
  isOpenMobile: boolean;
  setIsOpenMobile: (open: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentRoute,
  navigate,
  isOpenMobile,
  setIsOpenMobile
}) => {
  const [traceablePct, setTraceablePct] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    if (currentRoute.startsWith('/audit/') && currentRoute !== '/audit/new') {
      const auditId = currentRoute.replace('/audit/', '');
      fetchAudit(auditId).then(data => {
        if (!alive || !data || !data.claims) return;
        const total = data.claims.length;
        const withEvidence = data.claims.filter(c => ((c.supporting_evidence?.length || 0) + (c.contradicting_evidence?.length || 0)) >= 1).length;
        const pct = total > 0 ? Math.round((withEvidence / total) * 100) : 0;
        setTraceablePct(pct);
      }).catch(() => {});
    } else {
      setTraceablePct(null);
    }
    return () => { alive = false; };
  }, [currentRoute]);

  const mainNav = [
    { id: '/', label: 'Dashboard', icon: LayoutDashboard, badge: null },
    { id: '/audit/new', label: 'New Audit', icon: PlusCircle, badge: 'NEW' },
    { id: '/history', label: 'History', icon: History, badge: null },
    { id: '/settings', label: 'Settings', icon: Settings, badge: null },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpenMobile && (
        <div 
          className="fixed inset-0 bg-black/30 z-40 lg:hidden backdrop-blur-xs transition-opacity"
          onClick={() => setIsOpenMobile(false)}
        />
      )}

      {/* Persistent Sidebar (Section 3) */}
      <aside className={`
        fixed top-0 bottom-0 left-0 z-50 w-[240px] bg-white border-r border-[var(--line)] flex flex-col justify-between
        p-[28px_20px_24px] transition-transform duration-200 ease-in-out select-none
        ${isOpenMobile ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Top Header & Navigation */}
        <div className="space-y-8">
          {/* Logo & Brand Lockup */}
          <div className="flex items-center justify-between">
            <div 
              onClick={() => { navigate('/'); setIsOpenMobile(false); }}
              className="flex items-center gap-3 cursor-pointer group"
            >
              <LogoIcon size={36} />
              <div className="flex flex-col">
                <span className="font-extrabold text-[16px] text-[var(--ink)] tracking-[-0.01em] leading-tight">
                  Second Opinion
                </span>
                <span className="text-[11px] text-[var(--text-secondary)] font-normal leading-tight mt-0.5">
                  AI auditing platform
                </span>
              </div>
            </div>

            <button 
              onClick={() => setIsOpenMobile(false)} 
              className="lg:hidden text-[var(--text-secondary)] hover:text-[var(--ink)] p-1 rounded-lg hover:bg-[var(--surface-hover)]"
              aria-label="Close navigation"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation Items */}
          <nav className="space-y-1">
            {mainNav.map((item) => {
              const Icon = item.icon;
              const isAuditResults = currentRoute.startsWith('/audit/') && currentRoute !== '/audit/new';
              const isActive = item.id === '/' 
                ? (currentRoute === '/' || currentRoute === '') 
                : item.id === '/history'
                ? (currentRoute === '/history' || isAuditResults)
                : currentRoute === item.id;

              return (
                <button
                  key={item.id}
                  onClick={() => {
                    navigate(item.id);
                    setIsOpenMobile(false);
                  }}
                  aria-current={isActive ? 'page' : undefined}
                  className={`
                    w-full h-10 flex items-center justify-between px-3 rounded-[8px] text-[14px] transition-colors text-left
                    ${isActive 
                      ? 'bg-[var(--surface-hover)] text-[var(--ink)] font-bold' 
                      : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--ink)] font-semibold'}
                  `}
                >
                  <div className="flex items-center gap-3">
                    <Icon className="w-[18px] h-[18px] shrink-0" strokeWidth={isActive ? 2.2 : 1.9} />
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span className="text-[10px] font-extrabold tracking-[0.04em] px-2 py-0.5 rounded-full bg-[var(--accent-tint)] text-[var(--accent-text)]">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bottom "Audit Engine" card: pinned to the bottom, hairline border, radius 12px, padding 16px */}
        <div className="border border-[var(--line)] rounded-[12px] p-4 bg-white space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-bold text-[var(--ink)]">
              Audit engine
            </span>
            <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
          </div>
          
          {/* Progress bar */}
          <div className="w-full bg-[#EEF0F3] rounded-full h-1 overflow-hidden">
            <div 
              className="bg-[var(--ink)] h-1 rounded-full transition-all duration-300" 
              style={{ width: `${traceablePct !== null ? traceablePct : 100}%` }}
            />
          </div>
          
          <div className="flex items-center justify-between text-[12px] text-[var(--text-secondary)] font-normal">
            <span>SQLite persistent</span>
            <span>{traceablePct !== null ? `${traceablePct}% traceable` : '100% traceable'}</span>
          </div>
        </div>
      </aside>
    </>
  );
};
