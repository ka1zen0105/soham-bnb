import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { DashboardPage } from './pages/DashboardPage';
import { NewAuditPage } from './pages/NewAuditPage';
import { AuditResultsPage } from './pages/AuditResultsPage';
import { HistoryPage } from './pages/HistoryPage';
import { SettingsPage } from './pages/SettingsPage';

export function App() {
  const [currentRoute, setCurrentRoute] = useState<string>(() => {
    return window.location.pathname || '/';
  });
  const [isOpenMobile, setIsOpenMobile] = useState<boolean>(false);

  // Sync route with browser history
  useEffect(() => {
    const handlePopState = () => {
      setCurrentRoute(window.location.pathname || '/');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = (route: string) => {
    window.history.pushState({}, '', route);
    setCurrentRoute(route);
    window.scrollTo(0, 0);
  };

  // Determine active view
  let pageContent: React.ReactNode = null;
  let topBarTitle = 'Audit workspace';
  let breadcrumbs: { label: string; href?: string }[] = [];
  let isWhiteBg = false;

  if (currentRoute === '/' || currentRoute === '') {
    topBarTitle = 'Audit workspace';
    pageContent = <DashboardPage navigate={navigate} />;
    isWhiteBg = false;
  } else if (currentRoute.startsWith('/audit/new')) {
    topBarTitle = 'New audit';
    breadcrumbs = [{ label: 'Workspace', href: '/' }];
    pageContent = <NewAuditPage navigate={navigate} />;
    isWhiteBg = false;
  } else if (currentRoute.startsWith('/audit/')) {
    const auditId = currentRoute.split('?')[0].replace('/audit/', '');
    topBarTitle = 'Audit ledger';
    breadcrumbs = [
      { label: 'Workspace', href: '/' },
      { label: 'Audits', href: '/history' }
    ];
    pageContent = <AuditResultsPage auditId={auditId} navigate={navigate} />;
    isWhiteBg = true;
  } else if (currentRoute === '/history') {
    topBarTitle = 'Audit history';
    breadcrumbs = [{ label: 'Workspace', href: '/' }];
    pageContent = <HistoryPage navigate={navigate} />;
    isWhiteBg = false;
  } else if (currentRoute === '/settings') {
    topBarTitle = 'Settings & diagnostics';
    breadcrumbs = [{ label: 'Workspace', href: '/' }];
    pageContent = <SettingsPage />;
    isWhiteBg = false;
  } else {
    topBarTitle = 'Not found';
    pageContent = (
      <div className="p-12 text-center text-[var(--text-secondary)]">
        <h3 className="text-[16px] font-bold text-[var(--ink)]">Page Not Found</h3>
        <p className="text-[13px] mt-1 mb-4">The requested route does not exist.</p>
        <button
          onClick={() => navigate('/')}
          className="px-4 py-2 bg-[var(--ink)] text-white rounded-[10px] text-[12px] font-semibold"
        >
          Return to Workspace
        </button>
      </div>
    );
  }

  return (
    <div className={`min-h-screen text-[var(--ink)] flex ${isWhiteBg ? 'bg-white' : 'bg-[var(--bg-page)]'}`}>
      {/* Fixed Desktop Sidebar (240px) */}
      <Sidebar
        currentRoute={currentRoute}
        navigate={navigate}
        isOpenMobile={isOpenMobile}
        setIsOpenMobile={setIsOpenMobile}
      />

      {/* Main Workspace Area */}
      <div className="flex-1 lg:pl-[240px] flex flex-col min-w-0">
        <TopBar
          title={topBarTitle}
          breadcrumbs={breadcrumbs}
          onOpenMobileMenu={() => setIsOpenMobile(true)}
          navigate={navigate}
        />

        <main className={`flex-1 overflow-x-hidden ${isWhiteBg ? 'bg-white' : 'bg-[var(--bg-page)]'}`}>
          {pageContent}
        </main>
      </div>
    </div>
  );
}

export default App;
