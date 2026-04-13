import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Authenticator } from '@aws-amplify/ui-react';
import { Amplify } from 'aws-amplify';
import amplifyConfig from './amplifyconfiguration';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Navbar } from '@/components/Navbar';
import { Dashboard } from '@/pages/Dashboard';
import { Settings } from '@/pages/Settings';

// Configure Amplify
Amplify.configure(amplifyConfig);

function AppContent() {
  return (
    <Router>
      <div className="min-h-screen bg-slate-50 dark:bg-gray-950 transition-colors">
        <Navbar />
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <Authenticator>
        <AppContent />
      </Authenticator>
    </ErrorBoundary>
  );
}

export default App;
