import type { FloorPlanGeometry } from "@/lib/types";
import { FURNITURE_TYPE_LABELS, ROOM_TYPE_LABELS } from "@/lib/types";

const SEVERITY_STYLES: Record<string, string> = {
  error: "bg-red-100 text-red-800 border-red-300",
  warning: "bg-amber-100 text-amber-800 border-amber-300",
  info: "bg-blue-100 text-blue-800 border-blue-300",
};

export default function GeometryPanel({ geometry }: { geometry: FloorPlanGeometry }) {
  return (
    <div className="flex flex-col gap-4 text-sm">
      {geometry.scale_hint && (
        <p className="text-neutral-600">
          Erkannter Maßstab: <span className="font-medium">{geometry.scale_hint}</span>
        </p>
      )}

      <div>
        <h3 className="font-semibold mb-2">Räume ({geometry.rooms.length})</h3>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-neutral-300 text-neutral-500">
              <th className="py-1 pr-2">Name</th>
              <th className="py-1 pr-2">Typ</th>
              <th className="py-1 pr-2">Fläche</th>
            </tr>
          </thead>
          <tbody>
            {geometry.rooms.map((room) => (
              <tr key={room.id} className="border-b border-neutral-100">
                <td className="py-1 pr-2">{room.name}</td>
                <td className="py-1 pr-2">{ROOM_TYPE_LABELS[room.type]}</td>
                <td className="py-1 pr-2">
                  {room.area_m2 != null ? `${room.area_m2.toFixed(1)} m²` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="font-semibold mb-2">
          Wände ({geometry.walls.length}), Öffnungen (
          {geometry.walls.reduce((n, w) => n + w.openings.length, 0)})
        </h3>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-neutral-300 text-neutral-500">
              <th className="py-1 pr-2">ID</th>
              <th className="py-1 pr-2">Länge</th>
              <th className="py-1 pr-2">Stärke</th>
              <th className="py-1 pr-2">Außenwand</th>
              <th className="py-1 pr-2">Öffnungen</th>
            </tr>
          </thead>
          <tbody>
            {geometry.walls.map((wall) => {
              const length = Math.hypot(
                wall.end.x - wall.start.x,
                wall.end.y - wall.start.y,
              );
              return (
                <tr key={wall.id} className="border-b border-neutral-100">
                  <td className="py-1 pr-2 font-mono">{wall.id}</td>
                  <td className="py-1 pr-2">{length.toFixed(2)} m</td>
                  <td className="py-1 pr-2">{(wall.thickness_m * 100).toFixed(0)} cm</td>
                  <td className="py-1 pr-2">{wall.is_exterior ? "Ja" : "Nein"}</td>
                  <td className="py-1 pr-2">
                    {wall.openings.map((o) => (o.type === "door" ? "Tür" : "Fenster")).join(", ") ||
                      "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {geometry.furniture.length > 0 && (
        <div>
          <h3 className="font-semibold mb-2">
            Im Plan erkannte Möbel/Sanitärobjekte ({geometry.furniture.length})
          </h3>
          <p className="text-xs text-neutral-500 mb-2">
            Werden 1:1 aus dem Grundriss übernommen statt generisch platziert.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {geometry.furniture.map((item, i) => {
              const room = geometry.rooms.find((r) => r.id === item.room_id);
              return (
                <span
                  key={i}
                  className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs text-neutral-700"
                >
                  {FURNITURE_TYPE_LABELS[item.type]}
                  {room ? ` · ${room.name}` : ""}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {geometry.compliance_flags.length > 0 && (
        <div>
          <h3 className="font-semibold mb-2">Hinweise & Normprüfung</h3>
          <ul className="flex flex-col gap-2">
            {geometry.compliance_flags.map((flag, i) => (
              <li
                key={i}
                className={`border rounded-md px-3 py-2 ${SEVERITY_STYLES[flag.severity] ?? SEVERITY_STYLES.info}`}
              >
                <span className="font-medium">{flag.standard}:</span> {flag.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {geometry.source_notes && (
        <div>
          <h3 className="font-semibold mb-1">Anmerkungen des Parsers</h3>
          <p className="text-neutral-600">{geometry.source_notes}</p>
        </div>
      )}
    </div>
  );
}
