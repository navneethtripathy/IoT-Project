"""
CivicTwin-R — Chennai Real Geographical Datasets & Spatial Geometries
Contains verified geographic coordinates, hydrological waterway polylines,
catchment boundary polygons, 3D building footprints, rainfall stations, and reservoirs.

All coordinates use standard WGS84 [longitude, latitude] format for GeoJSON compatibility.
"""

from __future__ import annotations
from typing import Any, Dict, List

# ── 1. The 10 Prioritized Chennai Focus Locations ─────────────────────────
CHENNAI_LOCATIONS: List[Dict[str, Any]] = [
    {
        "id": "velachery",
        "name": "Velachery",
        "tamil_name": "வேளச்சேரி",
        "coordinates": [80.2180, 12.9815],
        "elevation_m": 6.2,
        "subbasin": "Kovalam / South Coastal",
        "area_km2": 18.4,
        "runoff_coefficient": 0.82,
        "flood_susceptibility": "Severe",
        "primary_hazard": "Topographic saucer depression, stormwater canal bottlenecks, lake surplus spill",
        "historical_peak_2015_m": 1.45,
        "historical_peak_2023_m": 1.62,
        "population_estimate": 240000,
        "key_infrastructure": ["Velachery MRTS Station", "Phoenix Marketcity", "Velachery Lake Surplus Channel"],
    },
    {
        "id": "pallikaranai",
        "name": "Pallikaranai Marsh",
        "tamil_name": "பள்ளிக்கரணை சதுப்புநிலம்",
        "coordinates": [80.2137, 12.9349],
        "elevation_m": 3.1,
        "subbasin": "Kovalam / South Coastal",
        "area_km2": 14.2,
        "runoff_coefficient": 0.65,
        "flood_susceptibility": "Critical / Natural Sink",
        "primary_hazard": "Major 800-ha freshwater wetland sink; receiving basin for 250 sq km South Chennai runoff",
        "historical_peak_2015_m": 2.10,
        "historical_peak_2023_m": 2.25,
        "population_estimate": 115000,
        "key_infrastructure": ["Pallikaranai Eco-Park", "Radial Road IT Corridor", "Okkiyam Maduvu Outlet Canal"],
    },
    {
        "id": "adyar",
        "name": "Adyar Estuary",
        "tamil_name": "அடையாறு முகத்துவாரம்",
        "coordinates": [80.2565, 13.0012],
        "elevation_m": 3.8,
        "subbasin": "Adyar Basin",
        "area_km2": 16.0,
        "runoff_coefficient": 0.75,
        "flood_susceptibility": "High",
        "primary_hazard": "Tidal backwater effect, coastal storm surge, Buckingham Canal confluence",
        "historical_peak_2015_m": 1.20,
        "historical_peak_2023_m": 1.15,
        "population_estimate": 180000,
        "key_infrastructure": ["Adyar Tholkappiya Poonga Eco-Park", "Malabar Hill", "Thiru Vi Ka Bridge"],
    },
    {
        "id": "madipakkam",
        "name": "Madipakkam",
        "tamil_name": "மடிப்பாக்கம்",
        "coordinates": [80.1961, 12.9647],
        "elevation_m": 5.4,
        "subbasin": "Kovalam / South Coastal",
        "area_km2": 12.1,
        "runoff_coefficient": 0.78,
        "flood_susceptibility": "Severe",
        "primary_hazard": "Inter-lake floodway encroachment; drains eastward to Pallikaranai marsh",
        "historical_peak_2015_m": 1.35,
        "historical_peak_2023_m": 1.50,
        "population_estimate": 160000,
        "key_infrastructure": ["Madipakkam Lake", "Medavakkam Main Road", "Keelkattalai Link Canal"],
    },
    {
        "id": "perungudi",
        "name": "Perungudi",
        "tamil_name": "பெருங்குடி",
        "coordinates": [80.2461, 12.9654],
        "elevation_m": 6.8,
        "subbasin": "Kovalam / South Coastal",
        "area_km2": 15.6,
        "runoff_coefficient": 0.85,
        "flood_susceptibility": "Moderate to High",
        "primary_hazard": "OMR IT corridor stormwater runoff, northern boundary of Pallikaranai marsh",
        "historical_peak_2015_m": 0.95,
        "historical_peak_2023_m": 1.10,
        "population_estimate": 175000,
        "key_infrastructure": ["OMR Technology Corridor", "Perungudi Lake", "Buckingham Canal Transfer"],
    },
    {
        "id": "tambaram",
        "name": "Tambaram",
        "tamil_name": "தாம்பரம்",
        "coordinates": [80.1000, 12.9249],
        "elevation_m": 28.5,
        "subbasin": "Adyar / Kovalam Headwaters",
        "area_km2": 34.2,
        "runoff_coefficient": 0.72,
        "flood_susceptibility": "Moderate",
        "primary_hazard": "Foothill runoff acceleration, Mudichur low-lying residential inundation",
        "historical_peak_2015_m": 1.80,
        "historical_peak_2023_m": 1.70,
        "population_estimate": 320000,
        "key_infrastructure": ["Tambaram Railway Junction", "GST Road Arterial", "Mudichur Flood Channel"],
    },
    {
        "id": "pallavaram",
        "name": "Pallavaram",
        "tamil_name": "பல்லாவரம்",
        "coordinates": [80.1491, 12.9675],
        "elevation_m": 18.2,
        "subbasin": "Adyar Basin",
        "area_km2": 19.8,
        "runoff_coefficient": 0.74,
        "flood_susceptibility": "Moderate",
        "primary_hazard": "Foothill surface runoff toward Pallavaram Lake & Chennai Airport boundary",
        "historical_peak_2015_m": 1.10,
        "historical_peak_2023_m": 1.05,
        "population_estimate": 215000,
        "key_infrastructure": ["Pallavaram Lake", "Chennai International Airport Perimeter", "GST Road"],
    },
    {
        "id": "chembarambakkam",
        "name": "Chembarambakkam Reservoir",
        "tamil_name": "செம்பரம்பாக்கம் ஏரி",
        "coordinates": [80.0575, 13.0116],
        "elevation_m": 25.4,
        "subbasin": "Adyar Basin",
        "area_km2": 358.0,
        "runoff_coefficient": 0.55,
        "flood_susceptibility": "Flood Regulator / Control Source",
        "primary_hazard": "Sluice gate surplus discharge directly feeds Adyar River headwaters (cap: 3,645 mcft / 103.2 MCM)",
        "historical_peak_2015_m": 2.80,
        "historical_peak_2023_m": 2.20,
        "population_estimate": 45000,
        "key_infrastructure": ["Chembarambakkam Masonry Dam & Sluice Gates", "Adyar River Headworks Regulator"],
    },
    {
        "id": "porur",
        "name": "Porur",
        "tamil_name": "போரூர்",
        "coordinates": [80.1565, 13.0382],
        "elevation_m": 14.1,
        "subbasin": "Adyar Basin",
        "area_km2": 22.4,
        "runoff_coefficient": 0.80,
        "flood_susceptibility": "Moderate",
        "primary_hazard": "Porur Lake surplus weir discharges into Adyar River via Manapakkam Channel",
        "historical_peak_2015_m": 1.15,
        "historical_peak_2023_m": 1.20,
        "population_estimate": 190000,
        "key_infrastructure": ["Porur Drinking Water Lake", "Mount-Poonamallee Road", "Ramachandra Medical Center"],
    },
    {
        "id": "saidapet",
        "name": "Saidapet (Adyar River Transit)",
        "tamil_name": "சைதாப்பேட்டை",
        "coordinates": [80.2231, 13.0213],
        "elevation_m": 8.0,
        "subbasin": "Adyar Basin",
        "area_km2": 28.5,
        "runoff_coefficient": 0.88,
        "flood_susceptibility": "Severe / Fluvial Bottleneck",
        "primary_hazard": "Adyar River central channel constricts at Maraimalai Adigal Bridge; major overtopping vulnerability",
        "historical_peak_2015_m": 2.40,
        "historical_peak_2023_m": 1.90,
        "population_estimate": 260000,
        "key_infrastructure": ["Maraimalai Adigal Saidapet Bridge", "Saidapet Metro Station", "Saidapet Causeways"],
    },
]


# ── 2. Chennai Waterways (GeoJSON FeatureCollection) ─────────────────────
# Georeferenced rivers, canals, marshes, and major reservoir polygons.
WATERWAYS_GEOJSON: Dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        # Adyar River (Main Channel Polyline from Chembarambakkam to Bay of Bengal)
        {
            "type": "Feature",
            "properties": {
                "id": "adyar_river",
                "name": "Adyar River",
                "type": "river",
                "length_km": 42.5,
                "max_discharge_cusecs": 55000,
                "color": "#06b6d4",
                "stroke_width": 5,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [80.0575, 13.0116],  # Chembarambakkam Outlet
                    [80.0820, 13.0105],  # Sirukalathur
                    [80.1150, 13.0130],  # Thiruneermalai reach
                    [80.1450, 13.0145],  # Anakaputhur
                    [80.1680, 13.0160],  # Manapakkam
                    [80.1890, 13.0185],  # Nandambakkam / MIOT
                    [80.2080, 13.0200],  # Jafferkhanpet
                    [80.2231, 13.0213],  # Saidapet Bridge
                    [80.2390, 13.0180],  # Kotturpuram
                    [80.2550, 13.0110],  # Malabar Hill / Chettinad Palace
                    [80.2720, 13.0100],  # Adyar Estuary (Bay of Bengal)
                ],
            },
        },
        # Cooum River (Main Channel Polyline across Central Chennai)
        {
            "type": "Feature",
            "properties": {
                "id": "cooum_river",
                "name": "Cooum River",
                "type": "river",
                "length_km": 68.0,
                "max_discharge_cusecs": 28000,
                "color": "#38bdf8",
                "stroke_width": 4,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [80.1450, 13.0720],  # Maduravoyal
                    [80.1950, 13.0650],  # Koyambedu
                    [80.2150, 13.0710],  # Aminjikarai
                    [80.2380, 13.0740],  # Chetpet
                    [80.2580, 13.0780],  # Egmore
                    [80.2730, 13.0760],  # Chintadripet
                    [80.2850, 13.0680],  # Napier Bridge (Bay of Bengal)
                ],
            },
        },
        # Buckingham Canal (North-South Inter-Basin Drainage Artery)
        {
            "type": "Feature",
            "properties": {
                "id": "buckingham_canal",
                "name": "Buckingham Canal",
                "type": "canal",
                "length_km": 35.0,
                "color": "#0284c7",
                "stroke_width": 3,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [80.2850, 13.0680],  # Cooum Confluence near Marina
                    [80.2780, 13.0450],  # Santhome reach
                    [80.2670, 13.0220],  # Mandaveli
                    [80.2580, 13.0080],  # Adyar confluence near Kotturpuram
                    [80.2540, 12.9850],  # Thiruvanmiyur
                    [80.2480, 12.9600],  # Perungudi / Kandanchavadi
                    [80.2430, 12.9350],  # Okkiyam Thorapakkam
                    [80.2380, 12.9000],  # Sholinganallur to Kovalam Estuary
                ],
            },
        },
        # Okkiyam Maduvu Surplus Channel (Transfers Pallikaranai marsh overflow to Buckingham Canal)
        {
            "type": "Feature",
            "properties": {
                "id": "okkiyam_maduvu",
                "name": "Okkiyam Maduvu Surplus Channel",
                "type": "channel",
                "length_km": 4.5,
                "color": "#0ea5e9",
                "stroke_width": 4,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [80.2180, 12.9380],  # Marsh East Outlet
                    [80.2290, 12.9370],  # Radial Road culvert
                    [80.2430, 12.9350],  # Confluence into Buckingham Canal
                ],
            },
        },
        # Pallikaranai Marsh Wetland Reserve (Polygon)
        {
            "type": "Feature",
            "properties": {
                "id": "pallikaranai_wetland",
                "name": "Pallikaranai Marsh Wetland Reserve",
                "type": "wetland",
                "area_ha": 800,
                "color": "#10b981",
                "fill_color": "#059669",
                "fill_opacity": 0.45,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.2050, 12.9550],
                        [80.2220, 12.9580],
                        [80.2280, 12.9450],
                        [80.2250, 12.9250],
                        [80.2150, 12.9200],
                        [80.2040, 12.9320],
                        [80.2010, 12.9450],
                        [80.2050, 12.9550],
                    ]
                ],
            },
        },
        # Chembarambakkam Reservoir (Polygon)
        {
            "type": "Feature",
            "properties": {
                "id": "chembarambakkam_lake",
                "name": "Chembarambakkam Reservoir",
                "type": "reservoir",
                "capacity_mcm": 103.2,
                "live_storage_mcm": 42.45,
                "color": "#0284c7",
                "fill_color": "#0369a1",
                "fill_opacity": 0.55,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.0400, 13.0100],
                        [80.0520, 13.0280],
                        [80.0750, 13.0250],
                        [80.0820, 13.0080],
                        [80.0700, 12.9980],
                        [80.0510, 12.9950],
                        [80.0400, 13.0100],
                    ]
                ],
            },
        },
        # Porur Lake (Polygon)
        {
            "type": "Feature",
            "properties": {
                "id": "porur_lake",
                "name": "Porur Lake (Drinking Water Reservoir)",
                "type": "lake",
                "capacity_mcm": 4.2,
                "color": "#0284c7",
                "fill_color": "#0369a1",
                "fill_opacity": 0.5,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.1500, 13.0320],
                        [80.1580, 13.0420],
                        [80.1650, 13.0400],
                        [80.1630, 13.0300],
                        [80.1540, 13.0280],
                        [80.1500, 13.0320],
                    ]
                ],
            },
        },
        # Velachery Lake (Polygon)
        {
            "type": "Feature",
            "properties": {
                "id": "velachery_lake",
                "name": "Velachery Lake",
                "type": "lake",
                "capacity_mcm": 1.8,
                "color": "#0284c7",
                "fill_color": "#0369a1",
                "fill_opacity": 0.5,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.2150, 12.9780],
                        [80.2220, 12.9830],
                        [80.2260, 12.9800],
                        [80.2230, 12.9740],
                        [80.2170, 12.9730],
                        [80.2150, 12.9780],
                    ]
                ],
            },
        },
    ],
}


# ── 3. Sub-Basin Catchments (GeoJSON FeatureCollection) ───────────────────
CATCHMENTS_GEOJSON: Dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "id": "catchment_velachery",
                "name": "Velachery Urban Sub-Basin",
                "mean_elevation_m": 6.2,
                "area_km2": 18.4,
                "c_runoff": 0.82,
                "outlet": "pallikaranai",
                "drainage_capacity_cusecs": 850,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.2050, 12.9920],
                        [80.2320, 12.9950],
                        [80.2350, 12.9720],
                        [80.2180, 12.9680],
                        [80.2040, 12.9780],
                        [80.2050, 12.9920],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "id": "catchment_pallikaranai",
                "name": "Pallikaranai Marsh Sink Basin",
                "mean_elevation_m": 3.1,
                "area_km2": 14.2,
                "c_runoff": 0.65,
                "outlet": "buckingham_canal",
                "drainage_capacity_cusecs": 1200,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.1980, 12.9600],
                        [80.2300, 12.9620],
                        [80.2350, 12.9200],
                        [80.2080, 12.9150],
                        [80.1950, 12.9350],
                        [80.1980, 12.9600],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "id": "catchment_saidapet_adyar",
                "name": "Saidapet - Mid Adyar Corridor",
                "mean_elevation_m": 8.0,
                "area_km2": 28.5,
                "c_runoff": 0.88,
                "outlet": "adyar_estuary",
                "drainage_capacity_cusecs": 45000,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.1950, 13.0350],
                        [80.2450, 13.0380],
                        [80.2520, 13.0100],
                        [80.2150, 13.0050],
                        [80.1900, 13.0150],
                        [80.1950, 13.0350],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "id": "catchment_madipakkam",
                "name": "Madipakkam Lowland Sub-Basin",
                "mean_elevation_m": 5.4,
                "area_km2": 12.1,
                "c_runoff": 0.78,
                "outlet": "pallikaranai",
                "drainage_capacity_cusecs": 600,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.1800, 12.9780],
                        [80.2040, 12.9780],
                        [80.2080, 12.9520],
                        [80.1820, 12.9500],
                        [80.1800, 12.9780],
                    ]
                ],
            },
        },
    ],
}


# ── 4. 3D Building Footprints (South Chennai Pilot Urban Zone) ───────────
# Georeferenced buildings with realistic heights for 3D extrusion rendering.
BUILDINGS_GEOJSON: Dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        # Velachery Commercial Hub (Phoenix / 100ft Road)
        {
            "type": "Feature",
            "properties": {"id": "bldg_01", "name": "Phoenix Marketcity Velachery", "height_m": 32, "floors": 8, "type": "commercial", "locality": "Velachery"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2170, 12.9910], [80.2195, 12.9910], [80.2195, 12.9885], [80.2170, 12.9885], [80.2170, 12.9910]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "bldg_02", "name": "Velachery MRTS Terminal", "height_m": 22, "floors": 5, "type": "transit", "locality": "Velachery"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2160, 12.9790], [80.2190, 12.9790], [80.2190, 12.9765], [80.2160, 12.9765], [80.2160, 12.9790]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "bldg_03", "name": "Vijayanagar Commercial Complex", "height_m": 18, "floors": 4, "type": "commercial", "locality": "Velachery"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2195, 12.9820], [80.2225, 12.9820], [80.2225, 12.9795], [80.2195, 12.9795], [80.2195, 12.9820]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "bldg_04", "name": "Tansi Nagar Residential Block", "height_m": 14, "floors": 4, "type": "residential", "locality": "Velachery"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2130, 12.9840], [80.2155, 12.9840], [80.2155, 12.9815], [80.2130, 12.9815], [80.2130, 12.9840]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "bldg_05", "name": "Baby Nagar Community Apartments", "height_m": 12, "floors": 3, "type": "residential", "locality": "Velachery"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2220, 12.9860], [80.2245, 12.9860], [80.2245, 12.9835], [80.2220, 12.9835], [80.2220, 12.9860]]]},
        },
        # Perungudi / OMR Tech Hub
        {
            "type": "Feature",
            "properties": {"id": "bldg_06", "name": "SP Infocity IT Park", "height_m": 38, "floors": 10, "type": "it_park", "locality": "Perungudi"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2450, 12.9660], [80.2490, 12.9660], [80.2490, 12.9625], [80.2450, 12.9625], [80.2450, 12.9660]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "bldg_07", "name": "RMZ Millenia Technology Park", "height_m": 42, "floors": 11, "type": "it_park", "locality": "Perungudi"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2420, 12.9710], [80.2460, 12.9710], [80.2460, 12.9675], [80.2420, 12.9675], [80.2420, 12.9710]]]},
        },
        # Saidapet Riverbank Buildings
        {
            "type": "Feature",
            "properties": {"id": "bldg_08", "name": "Saidapet Court Complex", "height_m": 16, "floors": 4, "type": "public", "locality": "Saidapet"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2210, 13.0240], [80.2240, 13.0240], [80.2240, 13.0215], [80.2210, 13.0215], [80.2210, 13.0240]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "bldg_09", "name": "Anna University Academic Block", "height_m": 24, "floors": 6, "type": "institutional", "locality": "Saidapet"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.2330, 13.0130], [80.2370, 13.0130], [80.2370, 13.0090], [80.2330, 13.0090], [80.2330, 13.0130]]]},
        },
        # Madipakkam Residential Zone
        {
            "type": "Feature",
            "properties": {"id": "bldg_10", "name": "Madipakkam High School & Center", "height_m": 12, "floors": 3, "type": "institutional", "locality": "Madipakkam"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.1940, 12.9660], [80.1970, 12.9660], [80.1970, 12.9635], [80.1940, 12.9635], [80.1940, 12.9660]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "bldg_11", "name": "Karthikeyapuram Residential Cluster", "height_m": 10, "floors": 3, "type": "residential", "locality": "Madipakkam"},
            "geometry": {"type": "Polygon", "coordinates": [[[80.1980, 12.9620], [80.2010, 12.9620], [80.2010, 12.9595], [80.1980, 12.9595], [80.1980, 12.9620]]]},
        },
    ],
}


# ── 5. Real Rainfall Monitoring Stations (CFM-DSS & IMD) ─────────────────
# Mapped to real geographical coordinates across the river catchments.
RAINFALL_STATIONS: List[Dict[str, Any]] = [
    {
        "station_id": "CHN06Z068W19",
        "station_name": "Saidapet Bridge Station",
        "subbasin": "Adyar",
        "coordinates": [80.2231, 13.0213],
        "rainfall_mm": 0.0,
        "previous_rainfall_mm": 0.0,
        "date": "2026-10-17T00:00:00",
        "time_of_measurement": "2026-10-17T23:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 8.0,
    },
    {
        "station_id": "CHN13Z183W44",
        "station_name": "Velachery Station",
        "subbasin": "Adyar / South Coastal",
        "coordinates": [80.2180, 12.9815],
        "rainfall_mm": 0.8,
        "previous_rainfall_mm": 1.2,
        "date": "2026-10-18T00:00:00",
        "time_of_measurement": "2026-10-18T15:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 6.2,
    },
    {
        "station_id": "CHN07Z086W25",
        "station_name": "Pallikaranai Wetland Station",
        "subbasin": "Kovalam / South Coastal",
        "coordinates": [80.2137, 12.9349],
        "rainfall_mm": 0.0,
        "previous_rainfall_mm": 0.0,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T22:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 3.1,
    },
    {
        "station_id": "CHN04Z040W15",
        "station_name": "Guindy Industrial Estate",
        "subbasin": "Adyar",
        "coordinates": [80.2120, 13.0080],
        "rainfall_mm": 0.0,
        "previous_rainfall_mm": 0.0,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T22:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 12.0,
    },
    {
        "station_id": "CHN05Z058W16",
        "station_name": "Koyambedu Market Station",
        "subbasin": "Cooum",
        "coordinates": [80.1950, 13.0650],
        "rainfall_mm": 0.0,
        "previous_rainfall_mm": 0.0,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T22:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 14.5,
    },
    {
        "station_id": "RPTWALVIS17",
        "station_name": "Tambaram Headwaters Station",
        "subbasin": "Kosasthalayar / Adyar",
        "coordinates": [80.1000, 12.9249],
        "rainfall_mm": 0.0,
        "previous_rainfall_mm": 0.0,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T22:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 28.5,
    },
    {
        "station_id": "CHN03Z022W11",
        "station_name": "Porur Lake Station",
        "subbasin": "Cooum / Adyar",
        "coordinates": [80.1565, 13.0382],
        "rainfall_mm": 0.0,
        "previous_rainfall_mm": 0.0,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T22:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 14.1,
    },
    {
        "station_id": "CHN02Z016W6",
        "station_name": "Taramani / OMR Station",
        "subbasin": "Cooum / South Coastal",
        "coordinates": [80.2461, 12.9654],
        "rainfall_mm": 0.0,
        "previous_rainfall_mm": 0.0,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T22:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 6.8,
    },
    {
        "station_id": "CGLMADKAR8",
        "station_name": "Madipakkam Rain Gauge",
        "subbasin": "Kosasthalayar / Kovalam",
        "coordinates": [80.1961, 12.9647],
        "rainfall_mm": 0.8,
        "previous_rainfall_mm": 0.8,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T11:30:00",
        "source": "observed",
        "provenance": "CFM-DSS_ARG",
        "status": "active",
        "elevation_m": 5.4,
    },
    {
        "station_id": "IMD_MEENAMBAKKAM",
        "station_name": "Meenambakkam IMD Observatory",
        "subbasin": "Adyar Basin",
        "coordinates": [80.1800, 12.9900],
        "rainfall_mm": 1.4,
        "previous_rainfall_mm": 0.6,
        "date": "2026-10-23T00:00:00",
        "time_of_measurement": "2026-10-23T23:30:00",
        "source": "observed",
        "provenance": "IMD_Chennai",
        "status": "active",
        "elevation_m": 16.0,
    },
]


# ── 6. Official Major Reservoirs (CFM-DSS & WRD) ──────────────────────────
CHENNAI_RESERVOIRS: List[Dict[str, Any]] = [
    {
        "tank_id": "TNCH-07-T0726",
        "reservoir_name": "Chembarambakkam",
        "tamil_name": "செம்பரம்பாக்கம்",
        "coordinates": [80.0575, 13.0116],
        "storage_capacity_live_mcm": 42.447,
        "storage_capacity_gross_mcm": 103.215,
        "storage_capacity_dead_mcm": 0.0,
        "storage_fill_pct": 41.12,
        "inflow_cusecs": 450,
        "outflow_cusecs": 250,
        "unit": "million_cubic_meters_MCM",
        "source": "observed",
        "provenance": "CFM-DSS_LakeOperationSystem",
        "role": "Controls primary headwater flood surge into Adyar River",
    },
    {
        "tank_id": "RD001",
        "reservoir_name": "Red Hills (Puzhal)",
        "tamil_name": "புழல் ஏரி",
        "coordinates": [80.1980, 13.1950],
        "storage_capacity_live_mcm": 68.385,
        "storage_capacity_gross_mcm": 93.446,
        "storage_capacity_dead_mcm": 0.07,
        "storage_fill_pct": 73.18,
        "inflow_cusecs": 600,
        "outflow_cusecs": 120,
        "unit": "million_cubic_meters_MCM",
        "source": "observed",
        "provenance": "CFM-DSS_LakeOperationSystem",
        "role": "Major drinking water reservoir for North & Central Chennai",
    },
    {
        "tank_id": "Po001",
        "reservoir_name": "Poondi (Sathyamurthy Sagar)",
        "tamil_name": "பூண்டி ஏரி",
        "coordinates": [79.8600, 13.1850],
        "storage_capacity_live_mcm": 13.818,
        "storage_capacity_gross_mcm": 91.492,
        "storage_capacity_dead_mcm": 5.0,
        "storage_fill_pct": 15.10,
        "inflow_cusecs": 300,
        "outflow_cusecs": 80,
        "unit": "million_cubic_meters_MCM",
        "source": "observed",
        "provenance": "CFM-DSS_LakeOperationSystem",
        "role": "Kosasthalaiyar river basin flood regulator",
    },
    {
        "tank_id": "Cho001",
        "reservoir_name": "Cholavaram",
        "tamil_name": "சோழவரம் ஏரி",
        "coordinates": [80.1450, 13.2350],
        "storage_capacity_live_mcm": 4.078,
        "storage_capacity_gross_mcm": 30.611,
        "storage_capacity_dead_mcm": 1.547,
        "storage_fill_pct": 13.32,
        "inflow_cusecs": 50,
        "outflow_cusecs": 15,
        "unit": "million_cubic_meters_MCM",
        "source": "observed",
        "provenance": "CFM-DSS_LakeOperationSystem",
        "role": "North Chennai retention and overflow balancing",
    },
    {
        "tank_id": "TK-001",
        "reservoir_name": "Thervoy Kandigai",
        "tamil_name": "தேர்வாய் கண்டிகை",
        "coordinates": [80.0100, 13.3800],
        "storage_capacity_live_mcm": 6.909,
        "storage_capacity_gross_mcm": 14.158,
        "storage_capacity_dead_mcm": 0.0,
        "storage_fill_pct": 48.80,
        "inflow_cusecs": 80,
        "outflow_cusecs": 0,
        "unit": "million_cubic_meters_MCM",
        "source": "observed",
        "provenance": "CFM-DSS_LakeOperationSystem",
        "role": "New reservoir supplying domestic and industrial water to North Chennai",
    },
]
