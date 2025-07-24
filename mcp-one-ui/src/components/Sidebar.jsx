import { Button } from "./ui/button";

export default function Sidebar({ onNavigate, activePage }) {
  const menu = [
    { id: "servers", label: "Servers" },
    { id: "tools", label: "Tools" },
    { id: "about", label: "About" },
  ];

  return (
    <aside className="h-screen w-64 bg-white border-r shadow-sm flex flex-col">
      <div className="p-4 border-b">
        <h2 className="text-xl font-bold">MCP One</h2>
      </div>
      <nav className="flex-1 p-4 space-y-2">
        {menu.map((item) => (
          <Button
            key={item.id}
            variant={activePage === item.id ? "default" : "ghost"}
            className="w-full justify-start"
            onClick={() => onNavigate(item.id)}
          >
            {item.label}
          </Button>
        ))}
      </nav>
      <div className="p-4 border-t text-xs text-gray-500">
        © {new Date().getFullYear()} MCP One
      </div>
    </aside>
  );
}
