# Places, search and routes (Round 2)

The viewer shows named places (points of interest), searches them, and draws a walkable route to the one you pick. The route is A* on the same collision grid that stops you at walls, so it never crosses a blocked cell.

## In the viewer

| Action | How |
|---|---|
| Find a place | `/` or `Ctrl+K`, then type. Typos and other names such as "almirah" work. |
| Pick a place | Click its label or its pin on the map, or aim at it and press `E`. |
| Go there | `G` walks the route, `F` flies there, `X` clears it. |

## Data

Places live in `site/assets/pois.json`, named by the `"pois"` key in `site/assets/manifest.json`. A scene without that key works as before, with no places.

```json
{ "id": "fridge", "name": "Fridge", "aliases": ["refrigerator"], "category": "appliance",
  "x": -0.22, "y": 0.81, "z": -1.37, "description": "Refrigerator in the kitchen corner" }
```

`x`, `y` and `z` are in metres, and `y` is height. An optional `"stand": {"x": 0, "z": 0}` sets where the visitor stands. Without it, the viewer picks a walkable spot about 1.2 m in front of the place.

## Tagging places (STEP 4)

1. Run `scripts/windows/step4_tag_places.bat`, or `python src/pipeline/step4_tag_places.py --site scenes/<name>/site` on any system.
2. The scene opens at `http://localhost:8766/?edit=1`.
3. Aim the centre dot at an object, press `T`, and type a name.
4. Press **Save to project**. The file is checked against the walkable grid, the old file is backed up to `tmp/poi_backups/`, and `pois.json` is written.

You can also edit `pois.json` by hand.

## Code

All in `src/viewer/`:

| File | Role |
|---|---|
| `nav.js` | A* pathfinding on the collision grid |
| `poi.js` | place search and spatial index |
| `poi_ui.js` | labels, search box, route drawing and map pins |
| `poi_editor.js` | the tagging tool |
| `main.js` | the viewer: renderer, movement, collision, live map |

## Tests

`node --test "tests/*.test.js"` runs 35 checks on the real scene grids and place files (Node.js 21 or newer).
