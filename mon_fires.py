# mon_fires.py
import requests

# حدود تقريبية للمملكة
KSA_BBOX = (34.0, 16.0, 56.0, 33.5)

def fetch_fires(map_key):
    if not map_key:
        return []

    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/VIIRS_SNPP_NRT/world/6"

    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return []

        lines = r.text.splitlines()
        if len(lines) <= 1:
            return []

        headers = lines[0].split(",")
        lat_i = headers.index("latitude")
        lon_i = headers.index("longitude")
        frp_i = headers.index("frp")

        fires = []
        for row in lines[1:]:
            cols = row.split(",")
            try:
                lat = float(cols[lat_i])
                lon = float(cols[lon_i])
                frp = float(cols[frp_i])
            except:
                continue

            if KSA_BBOX[0] <= lon <= KSA_BBOX[2] and KSA_BBOX[1] <= lat <= KSA_BBOX[3]:
                fires.append((lat, lon, frp))

        if not fires:
            return []

        max_frp = max(f[2] for f in fires)

        return [{
            "section": "fires",
            "title": f"🔥 حرائق نشطة داخل المملكة — عدد الرصد: {len(fires)}",
            "meta": {
                "count": len(fires),
                "max_frp": max_frp
            }
        }]

    except:
        return []
