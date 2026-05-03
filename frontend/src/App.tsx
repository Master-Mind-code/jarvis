import { useEffect, useState } from "react";
import { VoiceUI } from "./pages/VoiceUI";
import { OrionUI } from "./pages/OrionUI";
import { TradingUI } from "./pages/TradingUI";

type Route = "orion" | "voice" | "trading";

function pickRoute(pathname: string): Route {
  if (pathname.startsWith("/voice")) return "voice";
  if (pathname.startsWith("/trading")) return "trading";
  return "orion";
}

export default function App() {
  const [route, setRoute] = useState<Route>(() =>
    typeof window === "undefined" ? "orion" : pickRoute(window.location.pathname),
  );

  useEffect(() => {
    const onPop = () => setRoute(pickRoute(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  switch (route) {
    case "voice":   return <VoiceUI />;
    case "trading": return <TradingUI />;
    default:        return <OrionUI />;
  }
}
