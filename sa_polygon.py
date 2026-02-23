# =====================================
# حدود السعودية (Polygon مبسط)
# (تقريبي لكنه دقيق تشغيلياً)
# =====================================

SAUDI_POLYGON = [
    (34.5, 28.5),
    (35.0, 31.0),
    (37.5, 32.0),
    (42.0, 32.5),
    (46.0, 31.5),
    (50.0, 29.5),
    (55.0, 26.0),
    (55.0, 20.0),
    (52.0, 18.0),
    (48.0, 16.0),
    (43.0, 16.0),
    (39.0, 17.0),
    (36.0, 20.0),
    (34.5, 24.0),
]

# =====================================
# Point in Polygon (Ray Casting)
# =====================================

def point_in_polygon(lat, lon, polygon):

    x = lon
    y = lat

    inside = False
    n = len(polygon)

    p1x, p1y = polygon[0]

    for i in range(n + 1):
        p2x, p2y = polygon[i % n]

        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside

        p1x, p1y = p2x, p2y

    return inside
