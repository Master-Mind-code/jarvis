import { useEffect, useRef } from "react";
import { FLAT_SHAPES, SHAPES, shapeForName, shapeSphere, type Pt3, type ShapeName } from "@/lib/shapes";

export type SphereState = "idle" | "listening" | "processing" | "speaking";

interface SphereProps {
  state: SphereState;
  audioLevelRef: React.MutableRefObject<number>; // 0..1
  size?: number;
  particles?: number;
  cycleMs?: number;
  onShapeChange?: (label: string) => void;
}

const COLORS: Record<SphereState, [number, number, number]> = {
  idle:       [0, 229, 255],
  listening:  [255, 59, 92],
  processing: [245, 197, 24],
  speaking:   [0, 255, 163],
};

const SPEED: Record<SphereState, number> = {
  idle: 0.005, listening: 0.01, processing: 0.018, speaking: 0.014,
};

/**
 * Réseau neuronal 3D animé. Cycle entre 10 formes toutes les `cycleMs` ms.
 * État (couleur + vitesse + pulse) contrôlé par la prop `state`.
 * Le volume audio passé via ref pour réagir frame par frame sans re-render.
 */
export function Sphere({
  state,
  audioLevelRef,
  size = 380,
  particles: nParticles = 130,
  cycleMs = 7000,
  onShapeChange,
}: SphereProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // particle = position courante {x,y,z} ; les cibles {tx,ty,tz} sont en parallèle
  const particlesRef = useRef<(Pt3 & { tx: number; ty: number; tz: number })[]>([]);
  const stateRef = useRef<SphereState>(state);
  const isFlatRef = useRef(false);

  // Sync state dans une ref (évite recreation de la boucle anim)
  useEffect(() => { stateRef.current = state; }, [state]);

  // Init particules (forme sphère par défaut)
  useEffect(() => {
    const base = shapeSphere(nParticles, size * 0.36);
    particlesRef.current = base.map(p => ({ ...p, tx: p.x, ty: p.y, tz: p.z }));
  }, [nParticles, size]);

  // Cycle des formes toutes les `cycleMs` ms
  useEffect(() => {
    let idx = 0;
    const radius = size * 0.36;
    const setShape = (name: ShapeName) => {
      const target = shapeForName(name, nParticles, radius);
      const used = new Array(target.length).fill(false);
      const arr = particlesRef.current;
      for (let i = 0; i < arr.length; i++) {
        let bestJ = -1, bestD = Infinity;
        for (let j = 0; j < target.length; j++) {
          if (used[j]) continue;
          const dx = arr[i].x - target[j].x;
          const dy = arr[i].y - target[j].y;
          const dz = arr[i].z - target[j].z;
          const d = dx * dx + dy * dy + dz * dz;
          if (d < bestD) { bestD = d; bestJ = j; }
        }
        if (bestJ >= 0) {
          used[bestJ] = true;
          arr[i].tx = target[bestJ].x;
          arr[i].ty = target[bestJ].y;
          arr[i].tz = target[bestJ].z;
        }
      }
      isFlatRef.current = FLAT_SHAPES.has(name);
      onShapeChange?.(name);
    };
    const interval = window.setInterval(() => {
      idx = (idx + 1) % SHAPES.length;
      setShape(SHAPES[idx]);
    }, cycleMs);
    return () => window.clearInterval(interval);
  }, [cycleMs, nParticles, size, onShapeChange]);

  // Boucle d'animation
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = size, H = size, CX = W / 2, CY = H / 2;
    const CONNECT_DIST = Math.max(40, size * 0.14);
    let frame = 0, rotX = 0, rotY = 0;
    let rafId = 0;

    const project = (p: Pt3) => {
      const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
      let x = p.x * cosY - p.z * sinY;
      let z = p.x * sinY + p.z * cosY;
      const y = p.y * cosX - z * sinX;
      z = p.y * sinX + z * cosX;
      const persp = 380 / (380 + z);
      return { x: CX + x * persp, y: CY + y * persp, alpha: persp };
    };

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      const t = frame * 0.013;
      const st = stateRef.current;
      const lvl = audioLevelRef.current;

      const speed = isFlatRef.current ? 0 : SPEED[st];
      rotY += speed;
      rotX = isFlatRef.current ? 0 : Math.sin(t * 0.5) * 0.3;

      let pulse = 1;
      if (st === "listening")  pulse = 1 + lvl * 0.4 + Math.sin(t * 5) * 0.03;
      else if (st === "speaking") pulse = 1 + Math.abs(Math.sin(t * 9)) * 0.18 + Math.sin(t * 14) * 0.04;
      else if (st === "processing") pulse = 1 + Math.sin(t * 4) * 0.05;

      // Interpolation morphing
      const lerp = 0.06;
      for (const p of particlesRef.current) {
        p.x += (p.tx - p.x) * lerp;
        p.y += (p.ty - p.y) * lerp;
        p.z += (p.tz - p.z) * lerp;
      }

      const projected = particlesRef.current.map(p =>
        project({ x: p.x * pulse, y: p.y * pulse, z: p.z * pulse })
      );
      const [cr, cg, cb] = COLORS[st];

      // Lignes
      ctx.lineWidth = 1;
      for (let i = 0; i < projected.length; i++) {
        for (let j = i + 1; j < projected.length; j++) {
          const a = projected[i], b = projected[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < CONNECT_DIST) {
            const op = (1 - d / CONNECT_DIST) * 0.25 * Math.min(a.alpha, b.alpha);
            ctx.strokeStyle = `rgba(${cr},${cg},${cb},${op})`;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      // Points
      ctx.shadowColor = `rgba(${cr},${cg},${cb},0.8)`;
      ctx.shadowBlur = 8;
      for (const p of projected) {
        const sz = 1.5 + p.alpha * 2;
        const op = Math.min(1, p.alpha * 1.2);
        ctx.fillStyle = `rgba(${cr},${cg},${cb},${op})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, sz, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.shadowBlur = 0;

      frame++;
      rafId = window.requestAnimationFrame(draw);
    };
    draw();
    return () => window.cancelAnimationFrame(rafId);
  }, [size, audioLevelRef]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="block relative z-[3] -mt-10"
    />
  );
}
