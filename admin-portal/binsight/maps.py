from __future__ import annotations

import html
import json
from typing import Any, Iterable

import folium
import pandas as pd

from .config import Config
from .tracking import build_site_fill_profiles


SITE_STATE_PRIORITY = {
    "required": 1,
    "inspection": 2,
    "optional": 3,
    "completed": 4,
    "waiting": 5,
}
SITE_STATE_META = {
    "required": {"label": "Collection required", "symbol": "!", "color": "#f05a47"},
    "inspection": {"label": "Inspection required", "symbol": "?", "color": "#f2ad3f"},
    "optional": {"label": "Efficient pickup", "symbol": "+", "color": "#23a6a0"},
    "completed": {"label": "Service completed", "symbol": "✓", "color": "#55a879"},
    "waiting": {"label": "No collection required", "symbol": "·", "color": "#7f919b"},
}


def pilot_bounds(config: Config) -> list[list[float]]:
    return [
        [config.pilot.map_southwest_lat, config.pilot.map_southwest_lon],
        [config.pilot.map_northeast_lat, config.pilot.map_northeast_lon],
    ]


def coordinate_in_pilot(config: Config, latitude: float, longitude: float) -> bool:
    return (
        config.pilot.map_southwest_lat <= latitude <= config.pilot.map_northeast_lat
        and config.pilot.map_southwest_lon <= longitude <= config.pilot.map_northeast_lon
    )


def validate_pilot_extent(
    config: Config,
    bins: pd.DataFrame,
    route_points: Iterable[tuple[float, float]] = (),
) -> None:
    points = [
        (config.pilot.depot_lat, config.pilot.depot_lon),
        (config.pilot.recycling_facility_lat, config.pilot.recycling_facility_lon),
    ]
    points.extend(
        (float(row.latitude), float(row.longitude))
        for row in bins.drop_duplicates("site_id").itertuples()
    )
    points.extend((float(lat), float(lon)) for lat, lon in route_points)
    outside = [point for point in points if not coordinate_in_pilot(config, *point)]
    if outside:
        raise ValueError(
            "Pilot map bounds do not contain all depot/site/route coordinates: "
            + ", ".join(f"{lat:.6f},{lon:.6f}" for lat, lon in outside[:5])
        )


def _selection_state(selection: str) -> str:
    value = selection.strip().lower()
    if value in {"required", "unserved required", "collection required"}:
        return "required"
    if value in {"inspection required", "inspection/data review required"}:
        return "inspection"
    if value in {"co-located sibling", "efficient nearby pickup", "efficient pickup"}:
        return "optional"
    if value in {"completed", "service completed"}:
        return "completed"
    return "waiting"


def build_site_records(
    bins: pd.DataFrame,
    audit_rows: list[dict[str, Any]] | None = None,
    completed_bin_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    audit = {str(row.get("bin_id")): row for row in (audit_rows or [])}
    completed = set(completed_bin_ids or set())
    records: list[dict[str, Any]] = []
    for site_id, group in bins.groupby("site_id", sort=True):
        details = []
        for item in group.sort_values("bin_id").itertuples():
            row = audit.get(str(item.bin_id), {})
            selection = str(row.get("selection", row.get("collection_state", "Wait")))
            state = "completed" if str(item.bin_id) in completed else _selection_state(selection)
            details.append(
                {
                    "bin_id": str(item.bin_id),
                    "material_type": str(
                        getattr(item, "material_type", "mixed_general_waste")
                    ),
                    "state": state,
                    "collection_state": selection,
                    "fill_pct": row.get("fill_pct"),
                    "weight_kg": row.get("weight_kg"),
                    "time_to_overflow_hours": row.get("time_to_overflow_hours"),
                    "risk_level": str(row.get("risk_level", "unknown")),
                    "confidence_flag": row.get("confidence_flag"),
                    "selection_reason": str(
                        row.get("selection_reason", row.get("reason", selection.lower()))
                    ),
                }
            )
        state = min(
            (detail["state"] for detail in details),
            key=lambda value: SITE_STATE_PRIORITY[value],
        )
        attention = sum(detail["state"] in {"required", "inspection"} for detail in details)
        first = group.iloc[0]
        records.append(
            {
                "site_id": str(site_id),
                "site_label": str(first["site_label"]),
                "controller_id": str(first["controller_id"]),
                "latitude": float(first["latitude"]),
                "longitude": float(first["longitude"]),
                "state": state,
                "attention_count": int(attention),
                "bin_count": len(details),
                "bins": details,
            }
        )
    return records


def _format_value(value: Any, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "missing"
    if isinstance(value, bool):
        return "high" if value else "low"
    if isinstance(value, (int, float)):
        return f"{float(value):.1f}{suffix}"
    return html.escape(str(value))


def _site_popup(record: dict[str, Any]) -> str:
    rows = []
    for detail in record["bins"]:
        confidence = detail["confidence_flag"]
        confidence_text = "unknown" if confidence is None else ("high" if confidence else "low")
        rows.append(
            "<tr>"
            f"<th>{html.escape(detail['bin_id'])}</th>"
            f"<td>{html.escape(detail['material_type'].replace('_', ' ').title())}</td>"
            f"<td>{_format_value(detail['fill_pct'], '%')}</td>"
            f"<td>{_format_value(detail['weight_kg'], ' kg')}</td>"
            f"<td>{_format_value(detail['time_to_overflow_hours'], ' h')}</td>"
            f"<td>{html.escape(detail['risk_level'])}</td>"
            f"<td>{confidence_text}</td>"
            f"<td>{html.escape(detail['collection_state'])}</td>"
            f"<td>{html.escape(detail['selection_reason'])}</td>"
            "</tr>"
        )
    return (
        "<div class='site-popup'>"
        f"<h4>{html.escape(record['site_id'])} · {html.escape(record['site_label'])}</h4>"
        f"<p>{html.escape(record['controller_id'])} · {record['bin_count']} co-located underground bins</p>"
        "<div class='site-popup-scroll'><table><thead><tr>"
        "<th>Bin</th><th>Material</th><th>Fill</th><th>Weight</th><th>TTO</th><th>Risk</th>"
        "<th>Confidence</th><th>State</th><th>Reason</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div></div>"
    )


def create_restricted_map(config: Config, zoom_start: int | None = None) -> folium.Map:
    bounds = pilot_bounds(config)
    route_map = folium.Map(
        location=[config.pilot.center_lat, config.pilot.center_lon],
        zoom_start=zoom_start or config.pilot.map_min_zoom,
        min_zoom=config.pilot.map_min_zoom,
        max_zoom=config.pilot.map_max_zoom,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
        max_bounds=True,
    )
    route_map.options["maxBounds"] = bounds
    route_map.options["maxBoundsViscosity"] = 1.0
    # Public OpenStreetMap raster tiles require no application API key. Route,
    # site and facility overlays remain visible even if a tile request fails.
    folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="&copy; OpenStreetMap contributors; routes calculated with OSRM",
        name="OpenStreetMap · no API key",
        overlay=False,
        control=True,
        no_wrap=True,
        min_zoom=config.pilot.map_min_zoom,
        max_zoom=config.pilot.map_max_zoom,
        show=True,
    ).add_to(route_map)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr="&copy; OpenStreetMap contributors &copy; CARTO",
        name="CARTO light fallback · no API key",
        overlay=False,
        control=True,
        no_wrap=True,
        min_zoom=config.pilot.map_min_zoom,
        max_zoom=config.pilot.map_max_zoom,
        subdomains="abcd",
        show=False,
    ).add_to(route_map)
    boundary = folium.FeatureGroup(name="Optional pilot boundary", show=True)
    folium.Rectangle(
        bounds=bounds,
        color="#4d7485",
        weight=1,
        dash_array="5,7",
        fill=True,
        fill_color="#12303d",
        fill_opacity=0.035,
        tooltip="Configured Subang Jaya pilot boundary",
    ).add_to(boundary)
    boundary.add_to(route_map)
    folium.FitBounds(bounds, padding=(18, 18), max_zoom=config.pilot.map_min_zoom).add_to(route_map)
    map_name = route_map.get_name()
    reset_js = f"""
    window.addEventListener('load', function() {{
      const map = window['{map_name}'];
      if (!map) return;
      const bounds = {json.dumps(bounds)};
      const ResetControl = L.Control.extend({{
        options: {{position: 'topleft'}},
        onAdd: function() {{
          const button = L.DomUtil.create('button', 'binsight-reset leaflet-bar');
          button.type = 'button';
          button.title = 'Reset to Subang Jaya pilot bounds';
          button.setAttribute('aria-label', button.title);
          button.textContent = '⌂';
          L.DomEvent.disableClickPropagation(button);
          L.DomEvent.on(button, 'click', function() {{ map.fitBounds(bounds); }});
          return button;
        }}
      }});
      map.addControl(new ResetControl());
    }});
    """
    route_map.get_root().script.add_child(folium.Element(reset_js))
    return route_map


def _add_map_css(route_map: folium.Map) -> None:
    route_map.get_root().header.add_child(
        folium.Element(
            """
<style>
.leaflet-container{background:#e8ece8;color:#172126;font-family:Inter,Segoe UI,sans-serif;}
.leaflet-control-layers,.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#121e27;color:#e8f2f5;border:1px solid #304654;}
.leaflet-control-layers{max-width:min(280px,calc(100vw - 64px));font-size:12px;}
.leaflet-control-layers label{white-space:normal;}
.binsight-reset{width:30px;height:30px;background:#15242e;color:#8be7ff;border:0;font:700 18px monospace;cursor:pointer;}
.binsight-site-wrap{background:transparent;border:0;overflow:visible!important;}
.binsight-site-marker{position:relative;display:grid;place-items:center;width:34px;height:34px;background:var(--site-color);color:#071015;border:3px solid #e9f5f7;box-shadow:0 0 0 3px rgba(4,12,18,.74);font:900 16px/1 monospace;}
.binsight-site-marker.state-required{--site-color:#f05a47;clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%);}
.binsight-site-marker.state-inspection{--site-color:#f2ad3f;transform:rotate(45deg);border-radius:3px;}
.binsight-site-marker.state-inspection .site-symbol{transform:rotate(-45deg);}
.binsight-site-marker.state-optional{--site-color:#23a6a0;border-radius:50%;border-style:dashed;}
.binsight-site-marker.state-waiting{--site-color:#7f919b;border-radius:4px;}
.binsight-site-marker.state-completed,.binsight-site-marker.tracking-completed{--site-color:#55a879;clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);}
.binsight-site-marker.tracking-fill{background:linear-gradient(to top,var(--fill-color,#7f919b) 0 var(--fill-level,0%),#7f919b var(--fill-level,0%) 100%);transition:background .18s linear;}
.site-badge{position:absolute;right:-10px;top:-10px;min-width:24px;padding:3px 4px;border-radius:10px;background:#071015;color:#fff;border:1px solid #6f8794;font:700 9px/1 monospace;text-align:center;}
.site-popup{max-width:min(720px,80vw);font-size:12px}.site-popup h4{margin:0 0 4px;color:#8be7ff}.site-popup p{margin:0 0 8px;color:#a9bbc3}.site-popup-scroll{overflow:auto;max-width:100%}.site-popup table{border-collapse:collapse;min-width:680px}.site-popup th,.site-popup td{padding:5px 7px;border:1px solid #304654;text-align:left;vertical-align:top}.site-popup thead{background:#1d303d;color:#c9f3ff}
.ops-legend{position:absolute;z-index:999;right:10px;bottom:24px;max-width:min(310px,calc(100% - 20px));padding:9px 11px;border:1px solid #304654;border-radius:5px;background:rgba(10,19,26,.94);color:#dbe9ed;font:11px/1.45 monospace;box-sizing:border-box}.ops-legend b{color:#8be7ff}.legend-shape{display:inline-block;width:10px;height:10px;margin-right:5px;border:1px solid #eef8fa}.legend-line{display:inline-block;width:25px;height:3px;margin:0 6px 3px 0;background:#47d7ff;box-shadow:0 0 0 2px #08141b}
.dispatch-panel{position:absolute;z-index:1001;left:52px;top:10px;width:min(390px,calc(100% - 64px));padding:10px 12px;border:1px solid #355160;border-left:4px solid #47d7ff;border-radius:4px;background:rgba(7,15,21,.95);color:#e8f2f5;box-sizing:border-box;font:11px/1.35 monospace}.dispatch-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:8px}.dispatch-grid span{display:block;color:#78909b;font-size:9px;text-transform:uppercase}.dispatch-grid b{display:block;overflow:hidden;text-overflow:ellipsis;color:#e8f2f5;white-space:nowrap}.dispatch-controls{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.dispatch-controls button,.dispatch-controls select{min-height:30px;border:1px solid #446171;border-radius:3px;background:#152733;color:#dff7ff;font:700 10px monospace}.dispatch-controls button{padding:0 10px;cursor:pointer}.mock-label{color:#f2ad3f;font-weight:800}.truck-icon{position:relative;width:32px;height:32px;border-radius:50%;background:#07141b;border:2px solid #8be7ff;box-shadow:0 0 0 5px rgba(71,215,255,.19)}.truck-arrow{display:grid;place-items:center;width:100%;height:100%;color:#8be7ff;font:900 19px/1 monospace;transform-origin:50% 50%}.truck-icon::before{content:'';position:absolute;inset:-8px;border:1px solid #47d7ff;border-radius:50%;animation:truckPulse 1.7s ease-out infinite}@keyframes truckPulse{0%{transform:scale(.65);opacity:.75}100%{transform:scale(1.35);opacity:0}}@media (prefers-reduced-motion:reduce){.truck-icon::before{animation:none;display:none}.leaflet-zoom-animated{transition:none!important}}
@media(max-width:520px){.dispatch-panel{left:42px;top:8px;width:calc(100% - 50px);padding:8px}.dispatch-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ops-legend{font-size:9px;bottom:18px}.leaflet-control-layers{font-size:10px}}
</style>
"""
        )
    )


def add_controller_sites(
    route_map: folium.Map,
    site_records: list[dict[str, Any]],
    *,
    tracking_fill: bool = False,
) -> dict[str, folium.FeatureGroup]:
    layers = {
        "sites": folium.FeatureGroup(name="Controller sites", show=True),
        "required": folium.FeatureGroup(name="Collection-required sites", show=True),
        "inspection": folium.FeatureGroup(name="Inspection-required sites", show=True),
        "optional": folium.FeatureGroup(name="Efficient optional pickup sites", show=True),
    }
    for record in site_records:
        meta = SITE_STATE_META[record["state"]]
        tracking_class = " tracking-fill" if tracking_fill else ""
        marker_html = (
            f"<div class='binsight-site-marker state-{record['state']}{tracking_class}' "
            f"data-site-id='{html.escape(record['site_id'])}' "
            f"data-state='{record['state']}' title='{html.escape(meta['label'])}' "
            f"data-original-state='{record['state']}' data-original-symbol='{meta['symbol']}' "
            f"data-original-badge='{record['attention_count']}/{record['bin_count']}' "
            f"aria-label='{html.escape(record['site_id'])}: {html.escape(meta['label'])}; "
            f"{record['attention_count']} of {record['bin_count']} bins need attention'>"
            f"<span class='site-symbol'>{meta['symbol']}</span>"
            f"<span class='site-badge'>{record['attention_count']}/{record['bin_count']}</span>"
            "</div>"
        )
        folium.Marker(
            [record["latitude"], record["longitude"]],
            icon=folium.DivIcon(
                html=marker_html,
                class_name="binsight-site-wrap",
                icon_size=(34, 34),
                icon_anchor=(17, 17),
            ),
            tooltip=(
                f"{record['site_id']} · {meta['label']} · "
                f"{record['attention_count']}/{record['bin_count']}"
            ),
            popup=folium.Popup(_site_popup(record), max_width=760),
        ).add_to(layers["sites"])
        if record["state"] in {"required", "inspection", "optional"}:
            folium.CircleMarker(
                [record["latitude"], record["longitude"]],
                radius=20,
                color=meta["color"],
                weight=2,
                dash_array="2,5" if record["state"] != "required" else None,
                fill=False,
                tooltip=f"{record['site_id']} · {meta['label']}",
            ).add_to(layers[record["state"]])
    for layer in layers.values():
        layer.add_to(route_map)
    return layers


def add_depot(route_map: folium.Map, config: Config) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(name="Depot", show=True)
    folium.Marker(
        [config.pilot.depot_lat, config.pilot.depot_lon],
        tooltip=f"DEPOT · {config.pilot.depot_label}",
        icon=folium.DivIcon(
            html=(
                "<div style='display:grid;place-items:center;width:32px;height:32px;"
                "border-radius:50%;background:#55a879;color:#071015;border:3px solid #eaf7ef;"
                "box-shadow:0 0 0 3px #071015;font:900 14px monospace' aria-label='Depot'>D</div>"
            ),
            icon_size=(32, 32),
            icon_anchor=(16, 16),
        ),
    ).add_to(layer)
    layer.add_to(route_map)
    return layer


def add_recycling_facility(route_map: folium.Map, config: Config) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(name="Recycling facility", show=True)
    popup = (
        "<div class='site-popup'>"
        f"<h4>{html.escape(config.pilot.recycling_facility_label)}</h4>"
        "<p>Provisional demonstration unload destination for plastic, metal and glass. "
        "Vehicle acceptance and operating hours require field confirmation before deployment.</p>"
        "</div>"
    )
    folium.Marker(
        [config.pilot.recycling_facility_lat, config.pilot.recycling_facility_lon],
        tooltip=f"RECYCLING · {config.pilot.recycling_facility_label}",
        popup=folium.Popup(popup, max_width=420),
        icon=folium.DivIcon(
            html=(
                "<div style='display:grid;place-items:center;width:34px;height:34px;"
                "border-radius:50%;background:#287f83;color:#fff;border:3px solid #eaf7ef;"
                "box-shadow:0 0 0 3px #071015;font:900 14px monospace' "
                "aria-label='Recycling facility'>R</div>"
            ),
            icon_size=(34, 34),
            icon_anchor=(17, 17),
        ),
    ).add_to(layer)
    layer.add_to(route_map)
    return layer


def add_static_route_layers(
    route_map: folium.Map,
    active_geometries: list[list[tuple[float, float]]],
    reference_geometries: list[list[tuple[float, float]]] | None = None,
) -> None:
    active = folium.FeatureGroup(name="Active truck route", show=True)
    remaining = folium.FeatureGroup(name="Remaining route segments", show=False)
    completed = folium.FeatureGroup(name="Completed route segments", show=False)
    traffic = folium.FeatureGroup(name="Simulated traffic intensity", show=False)
    for trip_number, geometry in enumerate(active_geometries, start=1):
        folium.PolyLine(geometry, color="#071015", weight=10, opacity=.95).add_to(active)
        folium.PolyLine(
            geometry,
            color="#47d7ff",
            weight=5,
            opacity=.96,
            tooltip=f"Active simulated trip {trip_number}",
        ).add_to(active)
        folium.PolyLine(
            geometry,
            color="#f2ad3f",
            weight=8,
            opacity=.25,
            tooltip="Prototype traffic-intensity overlay",
        ).add_to(traffic)
    if reference_geometries:
        for geometry in reference_geometries:
            folium.PolyLine(
                geometry,
                color="#748996",
                weight=3,
                dash_array="7,7",
                opacity=.65,
                tooltip="Fixed-policy reference route",
            ).add_to(remaining)
    active.add_to(route_map)
    completed.add_to(route_map)
    remaining.add_to(route_map)
    traffic.add_to(route_map)


def _add_legend(route_map: folium.Map, include_tracking: bool = False) -> None:
    tracking = (
        "<br><span class='legend-line'></span> Current leg · serviced gauge resets to 0%"
        "<br><span class='legend-shape' style='background:linear-gradient(to top,#f05a47 75%,#7f919b 75%)'></span>"
        " Route-serviced fill: grey → red"
        if include_tracking
        else ""
    )
    legend = f"""
<div class="ops-legend" role="note" aria-label="Map legend">
  <b>DISPATCH MAP · SIMULATED</b><br>
  <span class="legend-shape" style="background:#f05a47"></span>! Collection required &nbsp;
  <span class="legend-shape" style="background:#f2ad3f;transform:rotate(45deg)"></span>? Inspection<br>
  <span class="legend-shape" style="background:#23a6a0;border-radius:50%"></span>+ Efficient pickup &nbsp;
  <span class="legend-shape" style="background:#7f919b"></span>· Can wait<br>
  <span class="legend-shape" style="background:#55a879"></span>✓ Completed
  <br><b>D</b> Waste depot &nbsp; <b>R</b> Recycling facility
  {tracking}
</div>
"""
    route_map.get_root().html.add_child(folium.Element(legend))


def finalize_map(route_map: folium.Map, config: Config, *, tracking: bool = False) -> folium.Map:
    _add_map_css(route_map)
    _add_legend(route_map, tracking)
    folium.LayerControl(collapsed=True, position="topright").add_to(route_map)
    return route_map


def build_overview_map(
    config: Config,
    bins: pd.DataFrame,
    routes: dict[str, Any],
    snapshot_rows: list[dict[str, Any]],
) -> folium.Map:
    smart: list[list[tuple[float, float]]] = []
    fixed: list[list[tuple[float, float]]] = []
    route_points: list[tuple[float, float]] = []
    for feature in routes.get("features", []):
        geometry = [(float(lat), float(lon)) for lon, lat in feature["geometry"]["coordinates"]]
        route_points.extend(geometry)
        if feature["properties"].get("policy") == "smart":
            smart.append(geometry)
        else:
            fixed.append(geometry)
    validate_pilot_extent(config, bins, route_points)
    route_map = create_restricted_map(config)
    add_static_route_layers(route_map, smart, fixed)
    add_controller_sites(route_map, build_site_records(bins, snapshot_rows))
    add_depot(route_map, config)
    add_recycling_facility(route_map, config)
    return finalize_map(route_map, config)


def build_dispatch_map(
    config: Config,
    bins: pd.DataFrame,
    geometries: list[list[tuple[float, float]]],
    audit_rows: list[dict[str, Any]],
) -> folium.Map:
    route_points = [point for geometry in geometries for point in geometry]
    validate_pilot_extent(config, bins, route_points)
    route_map = create_restricted_map(config)
    add_static_route_layers(route_map, geometries)
    add_controller_sites(route_map, build_site_records(bins, audit_rows))
    add_depot(route_map, config)
    add_recycling_facility(route_map, config)
    return finalize_map(route_map, config)


def build_tracking_map(
    config: Config,
    bins: pd.DataFrame,
    manifest: dict[str, Any],
    snapshot_rows: list[dict[str, Any]],
) -> folium.Map:
    route_points = [
        (float(point[0]), float(point[1]))
        for segment in manifest["segments"]
        for point in segment["geometry"]
    ]
    validate_pilot_extent(config, bins, route_points)
    route_map = create_restricted_map(config)
    site_records = build_site_records(bins, snapshot_rows)
    add_controller_sites(route_map, site_records, tracking_fill=True)
    add_depot(route_map, config)
    add_recycling_facility(route_map, config)
    active_layer = folium.FeatureGroup(name="Active truck route", show=True)
    completed_layer = folium.FeatureGroup(name="Completed route segments", show=True)
    remaining_layer = folium.FeatureGroup(name="Remaining route segments", show=True)
    traffic_layer = folium.FeatureGroup(name="Simulated traffic intensity", show=False)
    active_layer.add_to(route_map)
    completed_layer.add_to(route_map)
    remaining_layer.add_to(route_map)
    traffic_layer.add_to(route_map)

    map_name = route_map.get_name()
    active_name = active_layer.get_name()
    completed_name = completed_layer.get_name()
    remaining_name = remaining_layer.get_name()
    traffic_name = traffic_layer.get_name()
    manifest_json = json.dumps(manifest, separators=(",", ":")).replace("</", "<\\/")
    site_fill_profiles_json = json.dumps(
        build_site_fill_profiles(bins, snapshot_rows, manifest),
        separators=(",", ":"),
    ).replace("</", "<\\/")
    speeds = json.dumps(list(config.operations.tracking_speed_options))
    default_speed = int(config.operations.tracking_default_speed)
    panel = f"""
<div id="dispatch-panel-{map_name}" class="dispatch-panel" aria-live="polite">
  <div><span class="mock-label">LOCAL SIMULATION · NO LIVE VEHICLE</span> &nbsp; <b>{html.escape(manifest['route_id'])}</b></div>
  <div class="dispatch-grid">
    <div><span>Simulation time</span><b data-field="time">--</b></div>
    <div><span>Truck state</span><b data-field="status">PAUSED</b></div>
    <div><span>Trip</span><b data-field="trip">--</b></div>
    <div><span>Payload</span><b data-field="payload">--</b></div>
    <div><span>Next destination</span><b data-field="next">--</b></div>
    <div><span>Estimated arrival</span><b data-field="eta">--</b></div>
    <div><span>Completed</span><b data-field="completed">--</b></div>
    <div><span>Remaining</span><b data-field="remaining">--</b></div>
    <div><span>Elapsed</span><b data-field="elapsed">--</b></div>
  </div>
  <div class="dispatch-controls">
    <button type="button" data-action="resume">Resume</button>
    <button type="button" data-action="pause">Pause</button>
    <button type="button" data-action="reset">Reset</button>
    <select data-action="speed" aria-label="Demonstration speed"></select>
  </div>
</div>
"""
    route_map.get_root().html.add_child(folium.Element(panel))
    tracking_js = f"""
(window.addEventListener('load', function() {{
  const map = window['{map_name}'];
  if (!map) return;
  const manifest = {manifest_json};
  const siteFillProfiles = {site_fill_profiles_json};
  const activeLayer = window['{active_name}'];
  const completedLayer = window['{completed_name}'];
  const remainingLayer = window['{remaining_name}'];
  const trafficLayer = window['{traffic_name}'];
  const panel = document.getElementById('dispatch-panel-{map_name}');
  const speedOptions = {speeds};
  const speedSelect = panel.querySelector('[data-action="speed"]');
  speedOptions.forEach(value => {{
    const option = document.createElement('option');
    option.value = value; option.textContent = value + '× simulation';
    if (value === {default_speed}) option.selected = true;
    speedSelect.appendChild(option);
  }});
  let speed = {default_speed};
  let simMinute = manifest.start_minute;
  let running = false;
  let lastReal = null;
  let lastDraw = 0;
  const travel = manifest.segments.filter(row => row.kind === 'travel');
  const routeLines = travel.map(row => ({{
    segment: row,
    underlay: L.polyline(row.geometry, {{color:'#071015',weight:10,opacity:.94}}),
    line: L.polyline(row.geometry, {{color:'#315f77',weight:5,opacity:.82}})
  }}));
  routeLines.forEach(item => {{ item.underlay.addTo(remainingLayer); item.line.addTo(remainingLayer); }});
  travel.forEach(row => L.polyline(row.geometry, {{color:'#f2ad3f',weight:9,opacity:.18}}).addTo(trafficLayer));
  const icon = L.divIcon({{
    className:'', iconSize:[32,32], iconAnchor:[16,16],
    html:"<div class='truck-icon' aria-label='Simulated truck'><div class='truck-arrow'>▲</div></div>"
  }});
  const truck = L.marker(travel[0].geometry[0], {{icon:icon,zIndexOffset:1000}}).addTo(activeLayer);
  function field(name, value) {{ panel.querySelector('[data-field="'+name+'"]').textContent = value; }}
  function clock(minute) {{
    const day = Math.floor(minute / 1440) + 1;
    const within = Math.floor(minute % 1440);
    return 'D' + day + ' ' + String(Math.floor(within/60)).padStart(2,'0') + ':' + String(within%60).padStart(2,'0');
  }}
  function segmentAt(minute) {{
    const active=manifest.segments.find(row => minute >= row.start_minute && minute < row.end_minute);
    if (active) return active;
    let latest=manifest.segments[0];
    for (const row of manifest.segments) {{
      if (row.start_minute > minute) break;
      latest=row;
    }}
    return latest;
  }}
  function pointAt(row, minute) {{
    if (row.geometry.length === 1 || !row.cumulative_m || row.cumulative_m[row.cumulative_m.length-1] <= 0) return row.geometry[row.geometry.length-1];
    const fraction = Math.max(0,Math.min(1,(minute-row.start_minute)/(row.end_minute-row.start_minute)));
    const target = fraction * row.cumulative_m[row.cumulative_m.length-1];
    let index = 0;
    while (index < row.cumulative_m.length-2 && row.cumulative_m[index+1] < target) index++;
    const a=row.cumulative_m[index], b=row.cumulative_m[index+1];
    const local=b<=a?0:(target-a)/(b-a), p=row.geometry[index], q=row.geometry[index+1];
    return [p[0]+(q[0]-p[0])*local,p[1]+(q[1]-p[1])*local];
  }}
  function bearing(row, minute) {{
    const here=pointAt(row,minute), ahead=pointAt(row,Math.min(row.end_minute,minute+.05));
    return Math.atan2(ahead[1]-here[1],ahead[0]-here[0])*180/Math.PI + 90;
  }}
  function moveRouteLines(minute) {{
    [activeLayer,completedLayer,remainingLayer].forEach(layer => routeLines.forEach(item => {{layer.removeLayer(item.underlay);layer.removeLayer(item.line);}}));
    routeLines.forEach(item => {{
      const row=item.segment; let layer=remainingLayer, color='#315f77';
      if (minute >= row.end_minute) {{ layer=completedLayer;color='#537f70'; }}
      else if (minute >= row.start_minute) {{ layer=activeLayer;color='#47d7ff'; }}
      item.line.setStyle({{color:color,opacity:layer === remainingLayer ? .72 : .98}});
      item.underlay.addTo(layer); item.line.addTo(layer);
    }});
  }}
  function fillColor(fill) {{
    const ratio=Math.max(0,Math.min(1,fill/100));
    const grey=[127,145,155], red=[240,65,71];
    const rgb=grey.map((value,index)=>Math.round(value+(red[index]-value)*ratio));
    return 'rgb('+rgb.join(',')+')';
  }}
  function binFillAt(profile, minute) {{
    if (profile.completion_minute !== null && minute >= profile.completion_minute) return 0;
    const initial=Number(profile.initial_fill_pct || 0);
    const tto=profile.time_to_overflow_hours;
    if (tto === null || !Number.isFinite(Number(tto)) || Number(tto) <= 0) return initial;
    const elapsedHours=Math.max(0,minute-manifest.start_minute)/60;
    return Math.max(0,Math.min(100,initial+(100-initial)*elapsedHours/Number(tto)));
  }}
  function updateSites(minute) {{
    Object.entries(siteFillProfiles).forEach(([siteId, profiles]) => {{
      const routeProfiles=profiles.filter(profile=>profile.tracked_on_route);
      const displayedProfiles=routeProfiles.length ? routeProfiles : profiles;
      const siteFill=displayedProfiles.reduce((maximum,profile)=>Math.max(maximum,binFillAt(profile,minute)),0);
      const doneAt=(manifest.site_completion_minutes || {{}})[siteId];
      document.querySelectorAll('.binsight-site-marker[data-site-id="'+siteId+'"]').forEach(element => {{
        const isComplete = Number.isFinite(Number(doneAt)) && minute >= Number(doneAt);
        const displayedFill=isComplete ? 0 : siteFill;
        element.classList.remove('tracking-completed');
        element.querySelector('.site-symbol').textContent=element.dataset.originalSymbol;
        element.querySelector('.site-badge').textContent=Math.round(displayedFill)+'%';
        element.style.setProperty('--fill-level',displayedFill.toFixed(1)+'%');
        element.style.setProperty('--fill-color',fillColor(displayedFill));
        element.setAttribute('data-state',element.dataset.originalState);
        element.setAttribute('data-serviced',isComplete?'true':'false');
        element.setAttribute('title',siteId+' · route-serviced fill '+Math.round(displayedFill)+'%');
      }});
    }});
  }}
  function draw() {{
    const row=segmentAt(simMinute), point=pointAt(row,simMinute);
    truck.setLatLng(point);
    const arrow=truck.getElement()?.querySelector('.truck-arrow');
    if (arrow && row.kind==='travel' && simMinute < row.end_minute) arrow.style.transform='rotate('+bearing(row,simMinute)+'deg)';
    const completed=Object.values(manifest.completion_minutes||{{}}).filter(value=>value<=simMinute).length;
    const done=simMinute>=manifest.end_minute;
    field('time',clock(simMinute)); field('status',done?'TRIP_COMPLETE':row.status.replaceAll('_',' '));
    field('trip',String(row.trip_number));
    field('payload',(done?0:row.payload_kg).toFixed(0)+' / '+manifest.payload_capacity_kg.toFixed(0)+' kg');
    field('next',done?'COMPLETE':row.next_stop);
    field('eta',done?'—':clock(row.end_minute));
    field('completed',completed+' bins'); field('remaining',(manifest.total_bins-completed)+' bins');
    field('elapsed',(simMinute-manifest.start_minute).toFixed(1)+' min');
    moveRouteLines(simMinute); updateSites(simMinute);
  }}
  panel.querySelector('[data-action="resume"]').addEventListener('click',()=>{{running=true;lastReal=null;}});
  panel.querySelector('[data-action="pause"]').addEventListener('click',()=>{{running=false;field('status','PAUSED');}});
  panel.querySelector('[data-action="reset"]').addEventListener('click',()=>{{running=false;simMinute=manifest.start_minute;map.fitBounds({json.dumps(pilot_bounds(config))});draw();field('status','PAUSED');}});
  speedSelect.addEventListener('change',()=>{{speed=Number(speedSelect.value);}});
  window.binsightTracking = {{
    manifest: manifest,
    setSimulationMinute: value => {{
      running=false;
      simMinute=Math.max(manifest.start_minute,Math.min(manifest.end_minute,Number(value)));
      draw();
    }},
    getSimulationMinute: () => simMinute,
    getTruckPosition: () => truck.getLatLng(),
    isRunning: () => running
  }};
  function tick(timestamp) {{
    if (running) {{
      if (lastReal !== null) simMinute += (timestamp-lastReal)/1000 * speed/60;
      lastReal=timestamp;
      if (simMinute >= manifest.end_minute) {{simMinute=manifest.end_minute;running=false;}}
      if (timestamp-lastDraw>100) {{draw();lastDraw=timestamp;}}
    }} else lastReal=null;
    requestAnimationFrame(tick);
  }}
  draw(); requestAnimationFrame(tick);
}}));
"""
    route_map.get_root().script.add_child(folium.Element(tracking_js))
    return finalize_map(route_map, config, tracking=True)
