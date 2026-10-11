"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Environment, Grid, OrbitControls, PointerLockControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

/**
 * Begehbare Steuerung: WASD + Maus (Pointer-Lock). Nutzt dasselbe GLB wie die
 * Render-Stufe (docs/ARCHITECTURE.md) - keine zweite, abweichende Geometrie.
 */
function WalkControls({ enabled }: { enabled: boolean }) {
  const { camera } = useThree();
  const keys = useRef<Record<string, boolean>>({});
  const velocity = useRef(new THREE.Vector3());

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
    const direction = new THREE.Vector3();
    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();
    const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();

    if (keys.current["KeyW"]) direction.add(forward);
    if (keys.current["KeyS"]) direction.sub(forward);
    if (keys.current["KeyD"]) direction.add(right);
    if (keys.current["KeyA"]) direction.sub(right);

    if (direction.lengthSq() > 0) {
      direction.normalize().multiplyScalar(speed * delta);
      velocity.current.copy(direction);
      camera.position.add(velocity.current);
      camera.position.y = 1.7; // Augenhoehe
    }
  });

  return enabled ? <PointerLockControls /> : null;
}

export default function TourViewer({ modelUrl }: { modelUrl: string }) {
  const [walking, setWalking] = useState(false);

  return (
    <div className="relative w-full h-[480px] rounded-lg overflow-hidden border border-neutral-300 bg-neutral-100">
      <Canvas camera={{ position: [6, 4, 6], fov: 60 }} shadows>
        <ambientLight intensity={0.6} />
        <directionalLight position={[10, 10, 5]} intensity={1.2} castShadow />
        <Suspense fallback={null}>
          <Model url={modelUrl} />
          <Environment preset="apartment" />
        </Suspense>
        <Grid infiniteGrid fadeDistance={30} cellColor="#cccccc" sectionColor="#999999" />
        {walking ? <WalkControls enabled={walking} /> : <OrbitControls makeDefault />}
      </Canvas>

      <div className="absolute top-3 right-3 flex gap-2">
        <button
          onClick={() => setWalking((w) => !w)}
          className="px-3 py-1.5 text-sm rounded-md bg-neutral-900 text-white hover:bg-neutral-700 shadow"
        >
          {walking ? "Orbit-Ansicht" : "Begehen (WASD)"}
        </button>
      </div>
      {walking && (
        <div className="absolute bottom-3 left-3 text-xs text-neutral-700 bg-white/80 rounded px-2 py-1">
          Klicken zum Einrasten der Maus · WASD zum Laufen · ESC zum Beenden
        </div>
      )}
    </div>
  );
}
