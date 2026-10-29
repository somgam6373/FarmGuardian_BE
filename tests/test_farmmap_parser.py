from pathlib import Path

import pytest

from app.core.errors import AppError
from app.farm.infrastructure.integrations.farmmap import parse_farmmap_response

FIXTURE = Path(__file__).parent / "fixtures" / "farmmap_pnu_4182032521101610003.xml"

SQUARE = "0,0 10,0 10,10 0,10 0,0"
HOLE = "4,4 6,4 6,6 4,6 4,4"


def _polygon(outer: str, *holes: str) -> str:
    inner = "".join(
        f"<gml:innerBoundaryIs><gml:LinearRing><gml:coordinates>{h}</gml:coordinates>"
        "</gml:LinearRing></gml:innerBoundaryIs>"
        for h in holes
    )
    return (
        "<gml:polygonMember><gml:Polygon><gml:outerBoundaryIs><gml:LinearRing>"
        f"<gml:coordinates>{outer}</gml:coordinates></gml:LinearRing></gml:outerBoundaryIs>"
        f"{inner}</gml:Polygon></gml:polygonMember>"
    )


def _item(polygons: str | None = None, vdpt_yr: str | None = "2022-04-01") -> str:
    geometry = (
        ""
        if polygons is None
        else '<fmapBdcrd><gml:MultiPolygon srsName="EPSG:5179" '
        f'xmlns:gml="http://www.opengis.net/gml">{polygons}</gml:MultiPolygon></fmapBdcrd>'
    )
    year = "" if vdpt_yr is None else f"<vdptYr>{vdpt_yr}</vdptYr>"
    return (
        f"<item><fmapInnb>1</fmapInnb>{geometry}{year}"
        "<pnuLnmCd>4182032521101610003</pnuLnmCd><lnm>161-3전</lnm><intprNm>밭</intprNm></item>"
    )


def _response(code: str, items: str | None) -> str:
    body = "" if items is None else f"<body><items>{items}</items><totalCount>0</totalCount></body>"
    return f"<response><header><resultCode>{code}</resultCode></header>{body}</response>"


def _upstream_details(xml: str) -> dict:
    with pytest.raises(AppError) as exc:
        parse_farmmap_response(xml)
    assert exc.value.status == 502
    assert exc.value.code == "UPSTREAM_ERROR"
    return exc.value.details


def test_live_fixture_parses_two_parcels():
    parcels = parse_farmmap_response(FIXTURE.read_text(encoding="utf-8"))

    assert [(p.farmmap_id, p.pnu, p.lnm, p.land_use, p.vdpt_yr) for p in parcels] == [
        ("418203252100637", "4182032521101610003", "161-3전", "밭", 2022),
        ("418203252100655", "4182032521101600007", "160-7답", "논", 2020),
    ]
    ring = parcels[0].polygons[0][0]
    assert len(parcels[0].polygons) == 1 and len(parcels[0].polygons[0]) == 1
    assert ring[0] == (993833.485624643, 1970344.5561137851)
    assert ring[0] == ring[-1]


def test_code_00_is_success():
    assert len(parse_farmmap_response(_response("00", _item(_polygon(SQUARE))))) == 1


def test_code_3_without_body_is_empty():
    assert parse_farmmap_response(_response("3", None)) == []


def test_other_code_raises_with_upstream_code():
    assert _upstream_details(_response("22", None)) == {"source": "farmmap", "upstream_code": "22"}


def test_gateway_error_raises_with_reason_code():
    xml = (
        "<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
        "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
        "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
    )
    assert _upstream_details(xml) == {"source": "farmmap", "upstream_code": "30"}


def test_non_xml_raises_without_upstream_code():
    assert _upstream_details("<html>oops") == {"source": "farmmap"}


def test_item_without_geometry_raises():
    assert _upstream_details(_response("0", _item(None))) == {"source": "farmmap"}


def test_unparsable_coordinates_raise():
    xml = _response("0", _item(_polygon("0,0 abc 10,10 0,0")))
    assert _upstream_details(xml) == {"source": "farmmap"}


@pytest.mark.parametrize("coordinates", ["\n   ", "0,0 10,0 0,0", "0,0 10,0 10,10 0,10"])
def test_invalid_ring_raises(coordinates):
    # 공백뿐인 좌표, 점이 4개 미만인 링, 닫히지 않은 링
    xml = _response("0", _item(_polygon(coordinates)))
    assert _upstream_details(xml) == {"source": "farmmap"}


def test_inner_boundary_is_hole():
    [parcel] = parse_farmmap_response(_response("0", _item(_polygon(SQUARE, HOLE))))

    assert len(parcel.polygons[0]) == 2
    assert parcel.polygons[0][1][0] == (4.0, 4.0)


def test_multiple_polygon_members():
    xml = _response("0", _item(_polygon(SQUARE) + _polygon(HOLE)))
    assert len(parse_farmmap_response(xml)[0].polygons) == 2


def test_coordinates_with_whitespace():
    xml = _response("0", _item(_polygon(f"\n   {SQUARE.replace(' ', '  ')}\n  ")))
    assert len(parse_farmmap_response(xml)[0].polygons[0][0]) == 5


@pytest.mark.parametrize(
    "raw, year", [("2022", 2022), ("2022-04-01", 2022), ("", None), (None, None)]
)
def test_vdpt_yr(raw, year):
    [parcel] = parse_farmmap_response(_response("0", _item(_polygon(SQUARE), vdpt_yr=raw)))
    assert parcel.vdpt_yr == year
