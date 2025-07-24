import { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Toaster, toast } from "sonner";

export default function App() {
  const [activePage, setActivePage] = useState("servers");
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(false);

  // === API ===
  const fetchServers = async () => {
    try {
      setLoading(true);
      const res = await fetch("http://localhost:8000/servers");
      const data = await res.json();
      setServers(data.servers || []);
    } catch (error) {
      toast.error("Failed to fetch servers");
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    try {
      toast.info("Refreshing servers...");
      await fetch("http://localhost:8000/servers/refresh", { method: "POST" });
      toast.success("Servers refreshed!");
      fetchServers();
    } catch {
      toast.error("Failed to refresh");
    }
  };

  useEffect(() => {
    fetchServers();
  }, []);

  // === Render pages ===
  const renderContent = () => {
    if (activePage === "servers") {
      return (
        <div className="p-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {servers.length === 0 && (
            <p className="text-gray-500">No servers connected yet.</p>
          )}
          {servers.map((server, idx) => (
            <Card key={idx} className="shadow-sm border">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>{server.config.name}</span>
                  <span
                    className={`text-sm font-medium px-2 py-1 rounded ${
                      server.status === "online"
                        ? "bg-green-100 text-green-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {server.status}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-gray-600 mb-2">
                  <strong>URL:</strong> {server.config.url}
                </p>
                <p className="text-sm text-gray-600 mb-2">
                  <strong>Tools:</strong> {server.tools_count}
                </p>
                {server.error_message && (
                  <p className="text-sm text-red-500">
                    Error: {server.error_message}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      );
    }

    if (activePage === "tools") {
      return (
        <div className="p-6">
          <h2 className="text-xl font-bold mb-4">Tools</h2>
          <p>List of tools will appear here soon...</p>
        </div>
      );
    }

    if (activePage === "about") {
      return (
        <div className="p-6">
          <h2 className="text-xl font-bold mb-4">About</h2>
          <p className="text-gray-700">
            MCP One is your unified MCP Hub written in Python with a modern React UI.
          </p>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar onNavigate={setActivePage} activePage={activePage} />
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-white shadow-md p-4 flex items-center justify-between">
          <h1 className="text-2xl font-bold capitalize">{activePage}</h1>
          {activePage === "servers" && (
            <Button onClick={handleRefresh} disabled={loading}>
              {loading ? "Loading..." : "Refresh"}
            </Button>
          )}
        </header>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto bg-gray-100">{renderContent()}</main>
      </div>

      <Toaster richColors />
    </div>
  );
}
