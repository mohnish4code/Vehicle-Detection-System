import { Component, type ReactNode } from "react";
import { Toaster } from "react-hot-toast";
import { Link, Route, Routes } from "react-router-dom";
import { Header, MobileNav } from "./components/Header";
import { AlertIcon, ImageIcon } from "./components/icons";
import { OfflineBanner } from "./components/OfflineBanner";
import { btn, Card, cx, EmptyState } from "./components/ui";
import { HealthProvider } from "./health";
import { LogsPage } from "./pages/LogsPage";
import { ScanPage } from "./pages/ScanPage";

/** Last line of defence: a render error shows a friendly screen instead of a blank page */
class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error(error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Card className="mx-auto mt-10 max-w-md">
        <EmptyState
          tone="red"
          icon={<AlertIcon />}
          title="Something went wrong"
          message="The page hit an unexpected problem. Reloading usually fixes it."
          action={
            <button type="button" className={cx(btn.base, btn.primary)} onClick={() => window.location.reload()}>
              Reload
            </button>
          }
        />
      </Card>
    );
  }
}

function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={<ImageIcon />}
        title="Page not found"
        message="That page doesn't exist."
        action={
          <Link to="/" className={cx(btn.base, btn.primary)}>
            Go to Scan
          </Link>
        }
      />
    </Card>
  );
}

export default function App() {
  return (
    <HealthProvider>
      <Header />
      <main className="mx-auto max-w-6xl px-4 pb-28 pt-6 sm:pb-12 sm:pt-10">
        <OfflineBanner />
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<ScanPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </main>
      <footer className="mx-auto hidden max-w-6xl px-4 pb-8 text-xs text-slate-400 sm:block">
        YOLOv8 detection · PaddleOCR with plate-aware decoding · FastAPI · React
      </footer>
      <MobileNav />
      <Toaster
        position="top-center"
        containerStyle={{ top: 64 }}
        toastOptions={{
          duration: 4000,
          style: { borderRadius: "14px", fontSize: "14px", maxWidth: "420px", boxShadow: "0 8px 30px rgb(15 23 42 / 0.12)" },
        }}
      />
    </HealthProvider>
  );
}
