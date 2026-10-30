# Split preview and zone creation (design)

- Date: 2026-10-30
- Owner: Hyebin (farm context), issue #5
- Status: approved in chat (2026-10-30)
- Basis: `팜가디언_API_명세.md` §1, §2 (`Zone`, `ZoneSpec`, `SplitPiece`), §5 `split-preview`, `zones`;
  `팜가디언_아키텍처.md` §4 (`zone_service.create_many`), §7 「분할」;
  `2026-10-29-split-design.md` (`cut_positions`, merged in PR #9);
  `2026-10-29-fields-design.md` (fields, PR #22 — this work stacks on branch `feat/hb-fields`)

## Intent

After registering a field, the user splits it into zones by crop: choose a direction and ratios,
look at a preview, then confirm with a name, crop and optional planting date per zone. The preview
and the created zones must be identical, so the server recomputes the split on creation.

## Goals

1. `POST /fields/{field_id}/split-preview` — body `{direction: "crosswise"|"lengthwise", ratios}` →
   200 `[SplitPiece]` (`{geometry, area_m2}`), same length and order as `ratios`. Nothing saved.
2. `POST /fields/{field_id}/zones` — body `{direction, ratios, zones: [ZoneSpec]}` → 201 `[Zone]` in
   split order. `ZoneSpec = {name, crop_id, planted_at?}`.
3. Same input → same pieces, byte for byte (deterministic).

## Non-goals

- Re-split, merge, manual zones (P1 per arch §7; for now the user deletes the field and starts over).
- `GET/PATCH /zones/{id}` (#6), weather.

## Behaviour

### Validation (422 `VALIDATION_ERROR`)

- `direction`: one of the two values.
- `ratios`: 1–10 items, each an integer **1–100** (upper bound decided with Hyebin 2026-10-30: without
  it `[1, 1000000000]` gives a zero-area zone; 1:100 still allows a ~1 % zone). The API spec §5 and
  arch §7 get the same line.
- `zones` (create only): same length as `ratios`; `name` 1–30 chars after stripping spaces (same
  rule as field names); `crop_id` must exist in the `crop` table — otherwise
  `{loc: ["body", "zones", i, "crop_id"], type: "not_found"}` (my call, same style as unknown
  Farmmap ids); `planted_at` optional date (no future check — the spec has none).
- Ownership comes first: someone else's / unknown field → 404 even if the body is also wrong
  (`get_owned_field` runs as a dependency, like the judgment API).

### Split (arch §7)

1. Find the long side of the field from `ST_OrientedEnvelope(field.geom)` and its angle.
2. Rotate the field so the long side lies on the x axis. `crosswise` = cut lines parallel to the
   short side → vertical cuts in this frame → pieces follow the long side. `lengthwise` = cut lines
   parallel to the long side → rotate a further 90° so those lines are vertical too.
3. `cut_positions(rotated, ratios)` (pure, `farm/domain/split.py`) gives the x of each cut.
4. For each strip `[x_{k-1}, x_k]` (first starts left of the field, last ends right of it):
   `ST_Intersection` of the rotated field with that strip, rotate back with the same angle and
   origin, keep polygons only, `ST_Multi`.
5. Order ("the start of the direction", my call, fixed in map terms so it never flips between
   fields): normalise the long-side angle θ to (−90°, 90°], i.e. the long-side direction points
   east-ish (exactly north when the long side is vertical). `crosswise` pieces go along that
   direction → **west to east**. `lengthwise` pieces go along its left normal (θ + 90°) → **south to
   north**. In the rotated frame both are simply left to right. A concave field may give one strip
   several pieces — that is still one zone (MultiPolygon).
- `ratios == [n]` → one piece, the whole field.
- Geometry out as everywhere else: GeoJSON MultiPolygon, 1 decimal, no `crs`; `area_m2` 1 decimal.

### Create zones

- 409 `FIELD_ALREADY_SPLIT` if the field already has a zone.
- Two concurrent creates on the same field must not both succeed: lock the field row
  (`SELECT … FOR UPDATE`) before the "already split" check (my call).
- Insert one `zone` row per piece with the spec's name, crop, planted_at (`history_confirmed` default
  false), in split order, in one transaction; then commit in the route.
- Response `Zone` = `{id, field_id, name, crop: {id, name}, planted_at, history_confirmed, area_m2,
  geometry, bbox}` (API spec §2; bbox 1 decimal like fields).

## Code shape

- `farm/application/zone_service.py`: `create_many(db, field_id, user_id, parts) -> list[dict]`
  (name fixed by arch §4) — inserts zones and returns `Zone` dicts. Also hosts the `Zone` read used
  by the response (and later by #6).
- Split computation (rotate / cut / rotate back) is called by `field_service` for both endpoints so
  preview and create share one code path. SQL lives in `farm/infrastructure`.
- Routes in `farm/presentation/router.py`, models in `farm/presentation/schemas.py`.
- Left to the builder: how the rotated geometry is moved between PostGIS and Python (e.g. GeoJSON
  at full precision), rotation origin (e.g. the envelope centroid — anything fixed per field), strip
  rectangle bounds, which repository module holds the split SQL.

## Tests

DB tests with the existing fixtures; fields made from known polygons (insert SQL or
`field_repository.insert_field` with `tests/farm_support.square`).
- Axis-aligned 20×10 rectangle: crosswise `[1,1]` → two 10×10 pieces (100 ㎡ each, west then east);
  lengthwise `[1,1]` → two 20×5 strips (south then north); `[6,4]` areas 120 / 80 within 0.1 % of
  total. Same order for a 10×20 (north-south long side) field: crosswise south then north.
- Rotated rectangle (e.g. 30°): crosswise pieces are still cut across the long side (each piece's
  oriented long side is the original short side length, or areas match and pieces are disjoint).
- L-shaped field: areas match ratios within 0.1 %; a piece may be a MultiPolygon.
- Pieces cover the field: sum of areas equals the field area within 0.1 %; pieces don't overlap.
- Determinism: preview twice → identical JSON; create returns the same geometries as the preview.
- `[3]` → one piece equal to the field.
- 422 cases: bad direction, `[]`, 11 ratios, `0`, `-1`, `1.5`, `101`, zones length mismatch, empty /
  31-char / blank name, unknown `crop_id` (`loc` index).
- 404 for someone else's field (also with a bad body); 401 without header.
- 409 when zones already exist; nothing new inserted.
- After create, `GET /fields` shows the zones in its summaries.
