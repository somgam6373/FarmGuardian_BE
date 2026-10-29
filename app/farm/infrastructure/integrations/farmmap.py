import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx2

from app.core.config import settings
from app.core.errors import AppError
from app.farm.domain.geometry import MultiPolygon, Polygon, Ring

# 요청 URL에 인증키가 들어가므로 httpx2의 요청 로그(INFO)를 끈다
logging.getLogger("httpx2").setLevel(logging.WARNING)

PNU_URL = "http://apis.data.go.kr/B552895/getFarmmapService/getPnuBasedFarmmapInfo"
TIMEOUT_SECONDS = 5
GML = "{http://www.opengis.net/gml}"
OK_CODES = {"0", "00"}  # 명세서 예시는 00, 실제 응답은 0
NO_DATA_CODE = "3"  # 결과 없음. 오류가 아니다


@dataclass(frozen=True)
class FarmmapParcel:
    farmmap_id: str
    pnu: str
    lnm: str
    land_use: str
    vdpt_yr: int | None
    polygons: MultiPolygon


def _upstream_error(upstream_code: str | None = None) -> AppError:
    details = {"source": "farmmap"}
    if upstream_code is not None:
        details["upstream_code"] = upstream_code
    return AppError("UPSTREAM_ERROR", 502, "팜맵 조회에 실패했습니다", details)


def _ring(text: str | None) -> Ring:
    points = []
    for pair in (text or "").split():
        x, y = pair.split(",")
        points.append((float(x), float(y)))
    # 닫힌 링은 점이 4개 이상이고 첫 점과 끝 점이 같다
    if len(points) < 4 or points[0] != points[-1]:
        raise ValueError("invalid ring")
    return points


def _polygon(element: ET.Element) -> Polygon:
    outer = element.find(f"{GML}outerBoundaryIs/{GML}LinearRing/{GML}coordinates")
    if outer is None:
        raise ValueError("no outer boundary")
    holes = element.findall(f"{GML}innerBoundaryIs/{GML}LinearRing/{GML}coordinates")
    return [_ring(outer.text)] + [_ring(h.text) for h in holes]


def _vdpt_yr(text: str | None) -> int | None:
    # 명세서는 4자리 연도지만 실제 응답은 날짜(2022-04-01)라 앞 4자리만 쓴다
    head = (text or "")[:4]
    return int(head) if len(head) == 4 and head.isdigit() else None


def _parcel(item: ET.Element) -> FarmmapParcel:
    farmmap_id, pnu = item.findtext("fmapInnb"), item.findtext("pnuLnmCd")
    polygons = item.findall(f"fmapBdcrd/{GML}MultiPolygon/{GML}polygonMember/{GML}Polygon")
    if not farmmap_id or not pnu or not polygons:
        raise ValueError("missing required field")
    return FarmmapParcel(
        farmmap_id=farmmap_id,
        pnu=pnu,
        lnm=item.findtext("lnm", ""),
        land_use=item.findtext("intprNm", ""),
        vdpt_yr=_vdpt_yr(item.findtext("vdptYr")),
        polygons=[_polygon(p) for p in polygons],
    )


def parse_farmmap_response(xml: str) -> list[FarmmapParcel]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise _upstream_error() from None

    if root.tag == "OpenAPI_ServiceResponse":  # 키 오류 등 게이트웨이 형식
        raise _upstream_error(root.findtext("cmmMsgHeader/returnReasonCode"))
    if root.tag != "response":
        raise _upstream_error()

    code = root.findtext("header/resultCode")
    if code == NO_DATA_CODE:
        return []
    if code not in OK_CODES:
        raise _upstream_error(code)

    # totalCount는 실제 개수와 달라서 쓰지 않는다
    try:
        return [_parcel(item) for item in root.iterfind("body/items/item")]
    except ValueError:
        raise _upstream_error() from None


def parcels_by_pnu(pnu: str, *, client: httpx2.Client | None = None) -> list[FarmmapParcel]:
    params = {"serviceKey": settings.farmmap_api_key, "type": "xml", "pnuCode": pnu}
    try:
        if client is None:
            with httpx2.Client(timeout=TIMEOUT_SECONDS) as default_client:
                response = default_client.get(PNU_URL, params=params)
        else:
            response = client.get(PNU_URL, params=params)
    except httpx2.HTTPError:
        raise _upstream_error() from None
    # 키 오류는 HTTP 403이지만 본문에 오류 코드가 있으므로 상태 코드와 관계없이 본문을 읽는다
    return parse_farmmap_response(response.text)
