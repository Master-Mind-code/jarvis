import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Position = "top-left" | "top-right" | "bot-left" | "bot-right";

const POS_CLASSES: Record<Position, string> = {
  "top-left":  "top-[90px]   left-[30px]  text-left",
  "top-right": "top-[90px]   right-[30px] text-right",
  "bot-left":  "bottom-[230px] left-[30px]  text-left",
  "bot-right": "bottom-[230px] right-[30px] text-right",
};

interface HudReadoutProps {
  position: Position;
  label: string;
  values: { name?: string; value: string | number; format?: (v: any) => string }[];
}

export function HudReadout({ position, label, values }: HudReadoutProps) {
  return (
    <div className={cn("fixed font-mono text-[9px] tracking-[1px] leading-[1.8] text-text-dim z-10", POS_CLASSES[position])}>
      {label}<br />
      {values.map((v, i) => (
        <span key={i}>
          {v.name && <>{v.name}&nbsp;&nbsp;</>}
          <span className="hud-val">{v.format ? v.format(v.value) : v.value}</span>
          {i < values.length - 1 && <br />}
        </span>
      ))}
    </div>
  );
}

/** Bloc HUD avec valeurs flickerantes auto (CPU/temp/lat/pkt). */
export function SystemHud({ position }: { position: Position }) {
  const [load, setLoad]   = useState("72%");
  const [temp, setTemp]   = useState("38.0°C");

  useEffect(() => {
    const id = window.setInterval(() => {
      setLoad(Math.round(65 + Math.random() * 20) + "%");
      setTemp((38 + Math.random() * 4 - 2).toFixed(1) + "°C");
    }, 1200);
    return () => window.clearInterval(id);
  }, []);

  return (
    <HudReadout
      position={position}
      label="SYS / NEURAL"
      values={[
        { name: "LOAD", value: load },
        { name: "TEMP", value: temp },
      ]}
    />
  );
}

export function NetworkHud({ position }: { position: Position }) {
  const [lat, setLat] = useState("12ms");
  const [pkt, setPkt] = useState("99.8%");

  useEffect(() => {
    const id = window.setInterval(() => {
      setLat(Math.round(8 + Math.random() * 20) + "ms");
      setPkt((99.5 + Math.random() * 0.5).toFixed(1) + "%");
    }, 1200);
    return () => window.clearInterval(id);
  }, []);

  return (
    <HudReadout
      position={position}
      label="RÉSEAU"
      values={[
        { name: "LAT", value: lat },
        { name: "PKT", value: pkt },
      ]}
    />
  );
}

export function FreqHud({ position, rotation }: { position: Position; rotation: number }) {
  return (
    <HudReadout
      position={position}
      label=""
      values={[
        { name: "ROT",  value: rotation.toFixed(2) },
        { name: "FREQ", value: "1.4kHz" },
      ]}
    />
  );
}

export function ShapeHud({ position, label }: { position: Position; label: string }) {
  return (
    <HudReadout position={position} label="SHAPE" values={[{ value: label }]} />
  );
}
