"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  ContactShadows,
  OrbitControls,
  PointerLockControls,
  useGLTF,
} from "@react-three/drei";
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

function getOverviewView(rooms: Room[]): {
  position: [number, number, number];
  target: [number, number, number];
} {
  const points = rooms.flatMap((room) => room.polygon);
  if (points.length === 0) {
    return { position: [6, 8, 8], target: [0, 1, 0] };
  }

  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const width = Math.max(...xs) - Math.min(...xs);
  const depth = Math.max(...ys) - Math.min(...ys);
  const target: [number, number, number] = [
    (Math.min(...xs) + Math.max(...xs)) / 2,
    1.1,
    -(Math.min(...ys) + Math.max(...ys)) / 2,
  ];
  const fovRadians = THREE.MathUtils.degToRad(60);
  const distance = Math.max(width, depth) / (2 * Math.tan(fovRadians / 2)) * 1.25;

  return {
    position: [
      target[0] + distance * 0.58,
      target[1] + distance * 0.62,
      target[2] + distance * 0.58,
    ],
    target,
  };
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

  useFrame(() => {
    if (enabled && spawn && !spawnedRef.current) {
      camera.position.set(spawn.x, spawn.y, spawn.z);
      camera.lookAt(spawn.x, EYE_HEIGHT, spawn.z + 1.5);
      spawnedRef.current = true;
    }
    if (!enabled) spawnedRef.current = false;
  });

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
    if (!Number.isFinite(right.lengthSq()) || right.lengthSq() < 1e-6) {
      return;
    }

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

    const nextPosition = camera.position.clone();
    nextPosition.x += moveX.x * factorX;
    nextPosition.z += moveZ.z * factorZ;
    nextPosition.y = EYE_HEIGHT;
    camera.position.copy(nextPosition);
  });

  return enabled ? <PointerLockControls /> : null;
}

export default function TourViewer({ modelUrl, rooms = [] }: { modelUrl: string; rooms?: Room[] }) {
  const [walking, setWalking] = useState(false);
  const [spawn, setSpawn] = useState<THREE.Vector3 | null>(null);

  const mainRoom = useMemo(() => pickMainRoom(rooms), [rooms]);
  const overviewView = useMemo(() => getOverviewView(rooms), [rooms]);

  function startWalking(room?: Room) {
    const target = room ?? mainRoom;
    setSpawn(target ? roomCenterToWorld(target) : new THREE.Vector3(0, EYE_HEIGHT, 0));
    setWalking(true);
  }

  return (
    <div className="relative w-full h-[520px] rounded-lg overflow-hidden border border-neutral-300 bg-neutral-100">
      <Canvas camera={{ position: overviewView.position, fov: 60 }} shadows dpr={[1, 2]}>
        <color attach="background" args={["#f3f0eb"]} />
        <hemisphereLight intensity={1.1} groundColor="#aaa49b" color="#f4f2ed" />
        <directionalLight
          position={[5, 12, 7]}
          intensity={1.4}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
        />
        <Suspense fallback={null}>
          <Model url={modelUrl} />
        </Suspense>
        <ContactShadows position={[0, -0.04, 0]} opacity={0.28} scale={20} blur={2.5} far={8} />
        {walking ? (
          <WalkControls enabled={walking} spawn={spawn} />
        ) : (
          <OrbitControls
            makeDefault
            target={overviewView.target}
            enableDamping
            dampingFactor={0.08}
          />
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
