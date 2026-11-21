import { Component, useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import { UIProvider } from "./components/ui.jsx";
import { useHashRoute, usePolling } from "./hooks/useApi.js";
import { api } from "./services/api.js";
import Dashboard from "./pages/Dashboard.jsx";
import Projects from "./pages/Projects.jsx";
import Batches from "./pages/Batches.jsx";
import BatchDetail from "./pages/BatchDetail.jsx";
import Templates from "./pages/Templates.jsx";
import Review from "./pages/Review.jsx";
import Models from "./pages/Models.jsx";
import Exports from "./pages/Exports.jsx";
import Settings from "./pages/Settings.jsx";

/** Tangkap error tampilan agar halaman tidak menjadi kosong; tampilkan pesan + tombol muat ulang. */
class PageBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("Kesalahan halaman:", error, info?.componentStack); }
  componentDidUpdate(prev) { if (prev.routeKey !== this.props.routeKey && this.state.error) this.setState({ error: null }); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page">
        <h1>Halaman gagal ditampilkan</h1>
        <div className="notice notice-err">
          <b>{String(this.state.error?.message || this.state.error)}</b>
          <span className="small">Kirim pesan ini ke pengembang bila masalah berulang. Data Anda tidak hilang.</span>
        </div>
        <div className="row">
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Muat ulang halaman</button>
          <a className="btn" href="#/">Ke Dashboard</a>
        </div>
      </div>
    );
  }
}

export default function App() {
  const route = useHashRoute();
  const [health, setHealth] = useState(null);
  const check = async () => {
    try { setHealth(await api.health()); } catch { setHealth(null); }
  };
  useEffect(() => { check(); }, []);
  usePolling(check, 10000);

  const [section, id] = route.parts;
  let page;
  switch (section) {
    case undefined: page = <Dashboard />; break;
    case "projects": page = <Projects projectId={id ? Number(id) : null} />; break;
    case "batches": page = id ? <BatchDetail batchId={Number(id)} /> : <Batches query={route.query} />; break;
    case "templates": page = <Templates />; break;
    case "review": page = <Review batchId={id ? Number(id) : null} query={route.query} />; break;
    case "models": page = <Models />; break;
    case "exports": page = <Exports />; break;
    case "settings": page = <Settings />; break;
    default: page = <div className="page"><h1>Halaman tidak ditemukan</h1></div>;
  }
  return (
    <UIProvider>
      <div className="app">
        <Sidebar current={section || ""} health={health} />
        <main className="content"><PageBoundary routeKey={route.path}>{page}</PageBoundary></main>
      </div>
    </UIProvider>
  );
}
