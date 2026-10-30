# Zone update and zone centroid (design)

- Date: 2026-10-30
- Owner: Hyebin (farm context), issue #6 (part)
- Status: approved in chat (2026-10-30)
- Basis: `팜가디언_API_명세.md` §2 (`Zone`), §5 `PATCH /zones/{id}`, §9 「조회수정」;
  `팜가디언_아키텍처.md` §4 (`zone_service.centroid_wgs84`), §5 (`history_confirmed` rule), §8 날씨 위치;
  `팜가디언_판정_규칙.md` ③ 횟수 창, 이력 확인; PRD 수정 제안 6 (작물 변경).
  Stacks on branch `feat/hb-zones` (#5, not merged yet).

## Intent

On the 「조회수정」 tab the farmer edits a zone: rename it, switch to a new crop (new season), set or
clear the planting date, and confirm 「누락 없음」 (all past sprays entered). The weather endpoint
(Junhyeok) needs the zone's position as longitude/latitude.

## Goals

1. `PATCH /zones/{zone_id}` — body, all optional: `{name?, crop_id?, planted_at?: date|null,
   history_confirmed?: bool}` → 200 `Zone` (same shape as zone creation).
2. `zone_service.centroid_wgs84(db, zone_id) -> WgsPoint(lon, lat)` for `kma.py`.
3. A planting date in the future is rejected (422), both here and in `POST /fields/{id}/zones`.

## Non-goals

- `GET /zones/{id}` — it needs `rotation` and `recent_judgments`, which need read functions in the
  judgment context that do not exist yet. Built when Junhyeok adds them (agreed with Hyebin).
- Weather itself, fallow zones without a crop (still an open question on issue #6; spec requires a crop).

## Behaviour of `PATCH`

Rules, in this order (API spec §5, arch §5):
1. **Crop change**: if `crop_id` is sent and differs from the current one, the new planting date is
   the sent `planted_at`, or `null` when not sent (new season, PRD 6). Spray records stay.
   Sending the current `crop_id` is not a change.
2. **Planting date**: `planted_at` sent → that value (`null` clears it); not sent → unchanged
   (except rule 1). "Not sent" and "sent as null" are different.
3. **「누락 없음」**: if the resulting `planted_at` differs from the stored one, `history_confirmed`
   becomes `false`, unless `history_confirmed` is sent in the same request — then the sent value.
   Otherwise the sent value or unchanged.
   - Verified against the judgment rules: with no planting date ③ is always `NEEDS_CHECK`, and ④
     looks at the last 3 records regardless of crop, so keeping the confirmation when only the crop
     changes (and the date stays empty) is correct. The literal spec rule stands.
4. `name`: stripped, 1–30 chars (same as fields and zone creation).

Validation (422 `VALIDATION_ERROR`):
- `null` for `name`, `crop_id` or `history_confirmed` (they cannot be cleared) — my call.
- Unknown `crop_id` → `{loc: ["body", "crop_id"], type: "not_found"}` (same style as zone creation).
- `planted_at` after today (KST, `app.core.time.today_kst`) → 422 at `["body", "planted_at"]`.
  Reason: ③ counts sprays on or after the planting date, so a future date would count none and
  could show 「가능」 for a drug already used up (agreed with Hyebin). Same check for each
  `zones[i].planted_at` in zone creation, mirroring the spray API's future-date rule.
- Empty body `{}` → 200 with the zone unchanged.
- Not mine / unknown → 404 via `get_owned_zone` (before body errors, like the other routes).

## `centroid_wgs84`

- `ST_Transform(ST_Centroid(zone.geom), 4326)` (arch §8) → `WgsPoint(lon: float, lat: float)`, a
  frozen dataclass so the caller cannot swap the order (my call). Full precision.
- Lives in `farm/application/zone_service.py` as named in arch §4. Takes `db` like every other
  service function.

## Builder's calls (from the review)

- The future-date check runs in the service with an injected `today` (from `today_kst()` in the
  route), like `spray_service.record_spray`, so tests can pin the date.
- PATCH: an unknown `crop_id` and a future `planted_at` in one request are reported together in one
  `errors` list. Zone creation: future dates are checked together with unknown crops, after the
  `FIELD_ALREADY_SPLIT` check (same place as the existing crop check).
- `centroid_wgs84` on an unknown zone → `AppError` 404 like `zone_reader.get_zone_context`;
  ownership is the weather route's job (`get_owned_zone`).

## Docs

- API spec §5: add 「`planted_at`은 오늘(KST) 이후 날짜 불가」 to `PATCH /zones/{id}` and to `ZoneSpec`
  / zone creation.

## Tests

- PATCH rules table: rename only; crop change without date → date `null`, confirmation reset when a
  date existed; crop change with date; same crop id → no change; date change → confirmation `false`;
  date change + `history_confirmed: true` → `true`; same date resent → confirmation kept; `null`
  date clears it (and resets confirmation if there was a date); confirm only.
- Crop change with an empty date and confirmation `true` → confirmation stays `true`.
- 422: future date (tomorrow KST), `null` name / crop / confirmation, blank or 31-char name, unknown
  crop; zone creation with a future date at `["body", "zones", i, "planted_at"]`.
- 404 for another user's zone (also with a bad body), 401 without header, `{}` → 200 unchanged.
- `centroid_wgs84`: a square zone at a known EPSG:5179 position → expected lon/lat (from PostGIS,
  e.g. compared with a direct `ST_Transform` of the point) and `lon` ≈ 126–130, `lat` ≈ 33–39 for a
  real Korean coordinate.
