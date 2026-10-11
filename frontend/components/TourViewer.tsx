"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Environment, Grid, OrbitControls, PointerLockControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { Room, RoomType } from "@/lib/types";
import { ROOM_TYPE_LABELS } from "@/lib/types";

const EYE_HEIGHT = 1.7;
const COLLISION_MARGIN = 0.35;

// Backend exportiert GLB in Y-up (siehe geometry.py::export_glb, Rotation
// Z-up -> Y-up): interne (x, y)-Grundrisskoordinate -> Three.js (x, *, -y).
function roomCenterToWorld(room: Room): THREE.Vector3 {
  const xs = room.polygon.map((p) => p.x);
  const ys = room.polygon.map((p) => p.y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  return new THREE.Vector3(cx, EYE_HEIGHT, -cy);
}

const PREFERRED_TYPES: RoomType[] = ["living_room", "kitchen", "bedroom", "bathroom"];

function pickMainRoom(rooms: Room[]): Room | null {
  if (rooms.length === 0) return null;
  const preferred = rooms.filter((r) => PREFERRED_TYPES.includes(r.type));
  const pool = preferred.length > 0 ? preferred : rooms;
  return pool.reduce((best, r) => ((r.area_m2 ?? 0) > (best.area_m2 ?? 0) ? r : best), pool[0]);
}

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

/**
 * Begehbare Steuerung: WASD + Maus (Pointer-Lock) mit einfacher
 * Kollisionserkennung gegen Waende (Raycasting), damit man wie in einem
 * Videospiel durchs Haus laeuft statt durch Waende zu clippen. Nutzt
 * dasselbe GLB wie die Render-Stufe (docs/ARCHITECTURE.md) - keine zweite,
 * abweichende Geometrie.
 */
function WalkControls({ enabled, spawn }: { enabled: boolean; spawn: THREE.Vector3 | null }) {
  const { camera, scene } = useThree();
  const keys = useRef<Record<string, boolean>>({});
  const raycaster = useRef(new THREE.Raycaster());
  const spawnedRef = useRef(false);

  useEffect(() => {
    if (enabled && spawn && !spawnedRef.current) {
      camera.position.copy(spawn);
      spawnedRef.current = true;
    }
    if (!enabled) spawnedRef.current = false;
  }, [enabled, spawn, camera]);

  useEffect(() => {
    const down = (e: KeyboardEvent) => (keys.current[e.code] = true);
    const up = (e: KeyboardEvent) => (keys.current[e.code] = false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  useFrame((_, delta) => {
    if (!enabled) return;
    const speed = 3.2;
    const moveDir = new THREE.Vector3();
    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();
    const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();

    if (keys.current["KeyW"]) moveDir.add(forward);
    if (keys.current["KeyS"]) moveDir.sub(forward);
    if (keys.current["KeyD"]) moveDir.add(right);
    if (keys.current["KeyA"]) moveDir.sub(right);

    if (moveDir.lengthSq() === 0) return;
    moveDir.normalize();
    const step = speed * delta;

    // Kollisionserkennung: pro Bewegungsachse pruefen, ob ein Hindernis
    // (Wand) im Weg steht, und diese Teilbewegung ggf. unterdruecken -
    // erlaubt "Entlanggleiten" an Waenden statt hart zu blockieren.
    const origin = camera.position.clone();
    const tryAxis = (axisDir: THREE.Vector3) => {
      if (axisDir.lengthSq() === 0) return 0;
      const dist = step * axisDir.length();
      raycaster.current.set(origin, axisDir.clone().normalize());
      raycaster.current.far = dist + COLLISION_MARGIN;
      const hits = raycaster.current.intersectObjects(scene.children, true);
      const blocked = hits.some((h) => h.distance < dist + COLLISION_MARGIN);
      return blocked ? 0 : 1;
    };

    const moveX = new THREE.Vector3(moveDir.x, 0, 0).multiplyScalar(step);
    const moveZ = new THREE.Vector3(0, 0, moveDir.z).multiplyScalar(step);
    const factorX = tryAxis(moveX);
    const factorZ = tryAxis(moveZ);

    camera.position.x += moveX.x * factorX;
    camera.position.z += moveZ.z * factorZ;
    camera.position.y = EYE_HEIGHT;
  });

  return enabled ? <PointerLockControls /> : null;
}

export default function TourViewer({ modelUrl, rooms = [] }: { modelUrl: string; rooms?: Room[] }) {
  const [walking, setWalking] = useState(false);
  const [spawn, setSpawn] = useState<THREE.Vector3 | null>(null);

  const mainRoom = useMemo(() => pickMainRoom(rooms), [rooms]);

  function startWalking(room?: Room) {
    const target = room ?? mainRoom;
    setSpawn(target ? roomCenterToWorld(target) : new THREE.Vector3(0, EYE_HEIGHT, 0));
    setWalking(true);
  }

  return (
    <div className="relative w-full h-[520px] rounded-lg overflow-hidden border border-neutral-300 bg-neutral-100">
      <Canvas camera={{ position: [6, 4, 6], fov: 60 }} shadows>
        <ambientLight intensity={0.6} />
        <directionalLight position={[10, 10, 5]} intensity={1.2} castShadow />
        <Suspense fallback={null}>
          <Model url={modelUrl} />
          <Environment preset="apartment" />
        </Suspense>
        <Grid infiniteGrid fadeDistance={30} cellColor="#cccccc" sectionColor="#999999" />
        {walking ? (
          <WalkControls enabled={walking} spawn={spawn} />
        ) : (
          <OrbitControls makeDefault />
        )}
      </Canvas>

      <div className="absolute top-3 right-3 flex gap-2">
        {walking ? (
          <button
            onClick={() => setWalking(false)}
            className="px-3 py-1.5 text-sm rounded-md bg-neutral-900 text-white hover:bg-neutral-700 shadow"
          >
            Orbit-Ansicht
          </button>
        ) : (
          <button
            onClick={() => startWalking()}
            className="px-3 py-1.5 text-sm rounded-md bg-accent text-white hover:opacity-90 shadow"
          >
            Rundgang starten
          </button>
        )}
      </div>

      {walking && rooms.length > 0 && (
        <div className="absolute top-3 left-3 flex flex-wrap gap-1.5 max-w-[70%]">
          {rooms.map((room) => (
            <button
              key={room.id}
              onClick={() => startWalking(room)}
              className="px-2.5 py-1 text-xs rounded-full bg-white/90 text-neutral-700 hover:bg-white shadow"
            >
              {room.name || ROOM_TYPE_LABELS[room.type]}
            </button>
          ))}
        </div>
      )}

      {walking && (
        <div className="absolute bottom-3 left-3 text-xs text-neutral-700 bg-white/80 rounded px-2 py-1">
          Klicken zum Einrasten der Maus · WASD zum Laufen · ESC zum Beenden · oben links: Raum anwählen
        </div>
      )}
    </div>
  );
}
