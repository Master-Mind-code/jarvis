interface SettingsPanelProps {
  open: boolean;
  serverUrl: string;
  setServerUrl: (v: string) => void;
  token: string;
  setToken: (v: string) => void;
  deviceId: string;
  setDeviceId: (v: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
}

export function SettingsPanel({
  open, serverUrl, setServerUrl, token, setToken, deviceId, setDeviceId,
  onConnect, onDisconnect,
}: SettingsPanelProps) {
  if (!open) return null;
  return (
    <div className="fixed top-[70px] right-5 w-80 z-30
                    bg-bg-3 backdrop-blur-panel border border-border-hi rounded
                    p-4">
      <div className="font-orbitron text-[10px] tracking-[3px] text-cyan uppercase mb-3.5">
        Paramètres
      </div>

      <Field label="URL Serveur" value={serverUrl} onChange={setServerUrl} placeholder="ws://localhost:8765" />
      <Field label="Token secret" value={token} onChange={setToken} type="password" placeholder="token serveur" />
      <Field label="Device ID"   value={deviceId} onChange={setDeviceId} placeholder="voice-browser" />

      <div className="flex gap-2 mt-3.5">
        <button
          onClick={onConnect}
          className="flex-1 py-2 bg-cyan/10 border border-border-hi rounded-sm
                     font-orbitron text-[9px] tracking-[2px] uppercase text-cyan
                     hover:bg-cyan/20 transition-all cursor-pointer"
        >
          Connecter
        </button>
        <button
          onClick={onDisconnect}
          className="flex-1 py-2 bg-red/[0.08] border border-red/35 rounded-sm
                     font-orbitron text-[9px] tracking-[2px] uppercase text-red
                     hover:bg-red/[0.18] transition-all cursor-pointer"
        >
          Déconnecter
        </button>
      </div>
    </div>
  );
}

function Field({
  label, value, onChange, type = "text", placeholder,
}: { label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string }) {
  return (
    <>
      <div className="font-mono text-[9px] tracking-[1.5px] text-text-dim uppercase mt-2.5 mb-1">
        {label}
      </div>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2.5 py-2 bg-black/40 border border-border rounded-sm
                   text-text font-mono text-[11px] outline-none
                   focus:border-cyan/50"
      />
    </>
  );
}
