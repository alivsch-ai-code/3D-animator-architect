# Test-Grundrisse

Für End-to-End-Tests der Parsing-Pipeline mit realen (nicht synthetischen)
Grundrissen unterschiedlicher Schwierigkeit:

| Datei | Quelle | Lizenz | Warum dieser Testfall |
|---|---|---|---|
| `davies_house_1951.png` | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Davies_House_Floor_Plan.png), Davies House, 1951 (Arthur Baldwinson/Phyllis Shillito) | Public Domain (gemeinfrei in USA & Australien) | Einfaches Einfamilienhaus, **keine Maßangaben/Maßstab** im Bild — testet Schätzfähigkeit des Parsers ohne explizite Zahlen |
| `hampton_court_apt_1911.png` | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Hampton_Court_Apt_Vancouver_floor_plan.png), Hampton Court Apartment House, Vancouver, 1911 | Public Domain (gemeinfrei in Kanada & USA) | Komplexes Mehrfamilienhaus-Geschoss mit vielen Einheiten, Erkern, unregelmäßigen Formen — Stresstest für Komplexität |
| `synthetic_simple_apartment.png` / `.pdf` | Selbst erstellt für dieses Projekt | - | Kontrollfall mit expliziten Maßangaben (m², 1:100-Maßstab) und PDF-Upload-Pfad |

Diese Bilder werden ausschließlich für Tests/Entwicklung verwendet, nicht als
Teil des ausgelieferten Produkts.
