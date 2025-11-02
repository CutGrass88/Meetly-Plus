import heapq
import os
from collections import deque

_AIRPORT_CACHE = None
_ROUTE_DIRECT_CACHE = None
_ROUTE_INBOUND_CACHE = None
_LAST_RESULTS_META = {"by_candidate": {}, "requested_origins": [], "ordered_candidates": []}
_ROUTE_DETAIL_CACHE = {}
_REACHABLE_CACHE = {}
_COLLECT_REACHABLE_CACHE = {}

numOrigins = 25
_LAYOVER_MINUTES = 75.0
_FALLBACK_PENALTY_MINUTES = 120.0
_MAX_ALLOWED_STOPS = 2


def LoadAirportData(path):
    airports = {}
    import csv

    with open(path, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        for parts in reader:
            if len(parts) < 8:
                continue
            iata = (parts[4] or "").strip().upper()
            if not iata or iata == "\\N":
                continue
            if parts[6] == "" or parts[7] == "":
                continue
            try:
                lat = float(parts[6])
                lon = float(parts[7])
            except ValueError:
                continue
            airports[iata] = {
                "lat": lat,
                "lon": lon,
                "name": parts[1],
                "country": parts[3],
            }
    return airports


def _airports_path():
    try:
        root = os.path.dirname(os.path.dirname(__file__))
    except Exception:
        root = os.getcwd()
    return os.path.join(root, "assets", "airports.dat")


def _routes_path():
    try:
        root = os.path.dirname(os.path.dirname(__file__))
    except Exception:
        root = os.getcwd()
    return os.path.join(root, "assets", "routes.dat")


def _get_airports():
    global _AIRPORT_CACHE
    if _AIRPORT_CACHE is None:
        _AIRPORT_CACHE = LoadAirportData(_airports_path())
    return _AIRPORT_CACHE


def LoadRouteData(path):
    import csv

    direct = {}
    inbound = {}
    with open(path, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        for parts in reader:
            if len(parts) < 8:
                continue
            airline = (parts[0] or "").strip().upper()
            src = (parts[2] or "").strip().upper()
            dest = (parts[4] or "").strip().upper()
            if not src or not dest or src == "\\N" or dest == "\\N":
                continue
            if len(src) != 3 or len(dest) != 3:
                continue
            stops_raw = (parts[7] or "").strip()
            try:
                stops = int(stops_raw or "0")
            except ValueError:
                stops = 0
            if stops != 0:
                continue
            src_map = direct.setdefault(src, {})
            entry = src_map.setdefault(dest, {"airlines": set()})
            if airline:
                entry["airlines"].add(airline)
            dest_map = inbound.setdefault(dest, {})
            entry_inbound = dest_map.setdefault(src, {"airlines": set()})
            if airline:
                entry_inbound["airlines"].add(airline)
    for src_code, destinations in direct.items():
        for dest_code, info in destinations.items():
            info["airlines"] = frozenset(info["airlines"])
    for dest_code, sources in inbound.items():
        for src_code, info in sources.items():
            info["airlines"] = frozenset(info["airlines"])
    return direct, inbound


def _get_routes():
    global _ROUTE_DIRECT_CACHE, _ROUTE_INBOUND_CACHE
    if _ROUTE_DIRECT_CACHE is None or _ROUTE_INBOUND_CACHE is None:
        try:
            _ROUTE_DIRECT_CACHE, _ROUTE_INBOUND_CACHE = LoadRouteData(_routes_path())
        except Exception:
            _ROUTE_DIRECT_CACHE, _ROUTE_INBOUND_CACHE = {}, {}
    return _ROUTE_DIRECT_CACHE, _ROUTE_INBOUND_CACHE


def _collect_reachable_sources(dest, inbound_routes, max_stops):
    cache_key = (dest, max_stops)
    cached = _COLLECT_REACHABLE_CACHE.get(cache_key)
    if cached is not None:
        return set(cached)

    if dest not in inbound_routes:
        return set()
    visited = {dest}
    reachable = set()
    frontier = {dest}
    for _ in range(max_stops + 1):
        next_frontier = set()
        for airport in frontier:
            for src in inbound_routes.get(airport, {}):
                if src not in visited:
                    visited.add(src)
                    reachable.add(src)
                    next_frontier.add(src)
        if not next_frontier:
            break
        frontier = next_frontier

    result = frozenset(reachable)
    _COLLECT_REACHABLE_CACHE[cache_key] = result
    return set(result)


def compute_top10(airportCodes):
    """Compute top 10 meeting candidates for given origin IATA codes.

    Returns a tuple of (rows, metadata) where rows are:
    [IATA, airport name, score, mean time (min), total CO2 (kg), total distance (km), connectivity summary]
    """
    global _LAST_RESULTS_META

    airports = _get_airports()
    routes_direct, routes_inbound = _get_routes()
    validated = ValidateOrigins(airportCodes, airports)
    if not validated:
        meta = {"by_candidate": {}, "requested_origins": [], "ordered_candidates": []}
        _LAST_RESULTS_META = meta
        return [], meta

    rows, metadata = EvaluateCandidatesRouteAware(validated, airports, routes_direct, routes_inbound)
    top_rows = rows[:10]
    ordered_codes = [row[0] for row in top_rows]
    metadata["ordered_candidates"] = ordered_codes
    metadata["by_candidate"] = {code: metadata["by_candidate"][code] for code in ordered_codes if code in metadata["by_candidate"]}
    metadata["requested_origins"] = list(validated)
    _LAST_RESULTS_META = metadata
    return top_rows, metadata


def ValidateOrigins(airportCodes, airports):
    origins = len(airportCodes)
    if origins > numOrigins or origins < 2:
        print(f"Invalid number of origins. Must be between 2 and {numOrigins}.")
        return False

    invalidCodes = []
    for code in airportCodes:
        code = code.upper()
        if code not in airports:
            invalidCodes.append(code)

    if len(invalidCodes) > 0:
        print("Invalid airport codes found: " + ", ".join(invalidCodes))
        return False

    print("All airport codes are valid.")
    return [code.upper() for code in airportCodes]


def HaversineDistance(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2

    R = 6371.0

    lat1_rad = radians(float(lat1))
    lon1_rad = radians(float(lon1))
    lat2_rad = radians(float(lat2))
    lon2_rad = radians(float(lon2))

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance


def CalculateTime(distance):
    cruiseSpeed = 875
    if distance <= 1e-6:
        return 0.0
    return 40 + ((distance * 60) / cruiseSpeed)


def CalculateCO2Emissions(distance):
    emissionsFactor = 115 / 1000
    emissions = distance * emissionsFactor
    return emissions


def _reachable_destinations(origin, direct_routes, max_stops):
    cache_key = (origin, max_stops)
    cached = _REACHABLE_CACHE.get(cache_key)
    if cached is not None:
        return set(cached)

    if origin not in direct_routes:
        return set()
    queue = deque([(origin, 0)])
    best_legs = {origin: 0}
    reachable = set()
    max_legs = max_stops + 1

    while queue:
        current, legs = queue.popleft()
        neighbors = direct_routes.get(current, {})
        if not neighbors:
            continue
        for nxt in neighbors:
            next_legs = legs + 1
            if next_legs > max_legs:
                continue
            prev = best_legs.get(nxt)
            if prev is not None and prev <= next_legs:
                continue
            best_legs[nxt] = next_legs
            reachable.add(nxt)
            queue.append((nxt, next_legs))

    result = frozenset(reachable)
    _REACHABLE_CACHE[cache_key] = result
    return set(result)


def _origin_centroid(origins, airports):
    coords = []
    for code in origins:
        info = airports.get(code)
        if not info:
            continue
        coords.append((float(info["lat"]), float(info["lon"])))
    if not coords:
        return None
    lat = sum(c[0] for c in coords) / len(coords)
    lon = sum(c[1] for c in coords) / len(coords)
    return (lat, lon)


def _select_candidate_codes(origins, airports, direct_routes):
    if not origins:
        return list(airports.keys())

    reachable_sets = []
    for raw in origins:
        code = raw.upper()
        reachable = _reachable_destinations(code, direct_routes, _MAX_ALLOWED_STOPS)
        reachable.add(code)
        reachable_sets.append(reachable)

    candidate_pool = set.intersection(*reachable_sets) if reachable_sets else set()
    if not candidate_pool:
        candidate_pool = set.union(*reachable_sets) if reachable_sets else set()
    if not candidate_pool:
        candidate_pool = set(airports.keys())

    filtered = [code for code in candidate_pool if code in airports]
    if not filtered:
        filtered = list(airports.keys())

    centroid = _origin_centroid(origins, airports)
    limit_upper = 200
    limit_lower = 80
    limit = max(limit_lower, min(limit_upper, len(filtered)))
    if len(filtered) > limit and centroid:
        lat0, lon0 = centroid

        def _dist(code):
            info = airports.get(code)
            if not info:
                return float("inf")
            return HaversineDistance(lat0, lon0, info["lat"], info["lon"])

        filtered.sort(key=_dist)
        filtered = filtered[:limit]
    elif len(filtered) > limit:
        filtered = sorted(filtered)[:limit]

    return filtered


def _format_connectivity_summary(stats):
    order = [
        ("direct", "Direct"),
        ("one_stop", "1-stop"),
        ("two_stop", "2-stop"),
        ("fallback", "Fallback"),
    ]
    parts = [f"{label} {stats.get(key, 0)}" for key, label in order]
    if stats.get("same", 0):
        parts.append(f"Local {stats['same']}")
    return " | ".join(parts)


def _fallback_route(origin, dest, airports):
    origin_data = airports.get(origin)
    dest_data = airports.get(dest)

    segments = []
    distance = 0.0
    base_time = 0.0
    co2 = 0.0
    if origin_data and dest_data:
        distance = HaversineDistance(origin_data["lat"], origin_data["lon"], dest_data["lat"], dest_data["lon"])
        base_time = CalculateTime(distance)
        co2 = CalculateCO2Emissions(distance)
        segments.append({
            "from": origin,
            "to": dest,
            "distance": distance,
            "time": base_time,
            "airlines": 0,
        })

    total_time = base_time + _FALLBACK_PENALTY_MINUTES
    return {
        "availability": "fallback",
        "legs": len(segments) if segments else 1,
        "stops": 0,
        "path": [origin, dest],
        "segments": segments,
        "distance": distance,
        "time": total_time,
        "co2": co2,
        "airlines": 0,
        "penalty_minutes": _FALLBACK_PENALTY_MINUTES,
        "layover_minutes": _FALLBACK_PENALTY_MINUTES,
    }


def _search_best_route(origin, dest, airports, direct_routes, inbound_routes, max_stops):
    reachable = _collect_reachable_sources(dest, inbound_routes, max_stops)
    if origin != dest and origin not in reachable and direct_routes.get(origin, {}).get(dest) is None:
        return None

    availability_labels = {0: "direct", 1: "one_stop", 2: "two_stop"}

    initial_state = (0.0, 0.0, 0.0, [origin], [], 0)
    heap = [initial_state]
    visited = {}

    while heap:
        total_time, total_distance, total_co2, path, segments, layovers = heapq.heappop(heap)
        current = path[-1]
        legs = len(path) - 1
        state_key = (current, legs)
        best_seen = visited.get(state_key)
        if best_seen is not None and total_time >= best_seen - 1e-6:
            continue
        visited[state_key] = total_time

        if current == dest and legs > 0:
            stops = len(path) - 2
            if stops <= max_stops:
                availability = availability_labels.get(stops, "two_stop")
                avg_airlines = 0.0
                if segments:
                    avg_airlines = sum(seg.get("airlines", 0) for seg in segments) / len(segments)
                return {
                    "availability": availability,
                    "legs": len(segments),
                    "stops": stops,
                    "path": path,
                    "segments": segments,
                    "distance": total_distance,
                    "time": total_time,
                    "co2": total_co2,
                    "airlines": round(avg_airlines, 3),
                    "layover_minutes": layovers,
                }
            continue

        if legs >= max_stops + 1:
            continue

        neighbors = direct_routes.get(current, {})
        if not neighbors:
            continue
        current_data = airports.get(current)
        if not current_data:
            continue

        for nxt, info in neighbors.items():
            if nxt in path:
                continue
            if nxt != dest and nxt not in reachable:
                continue
            nxt_data = airports.get(nxt)
            if not nxt_data:
                continue

            leg_distance = HaversineDistance(current_data["lat"], current_data["lon"], nxt_data["lat"], nxt_data["lon"])
            leg_time = CalculateTime(leg_distance)
            leg_co2 = CalculateCO2Emissions(leg_distance)
            layover_time = _LAYOVER_MINUTES if len(path) > 1 else 0.0
            new_total_time = total_time + layover_time + leg_time
            new_total_distance = total_distance + leg_distance
            new_total_co2 = total_co2 + leg_co2
            new_layovers = layovers + (layover_time if layover_time else 0.0)
            airlines_count = len(info.get("airlines", ())) if info.get("airlines") else 0
            segment = {
                "from": current,
                "to": nxt,
                "distance": leg_distance,
                "time": leg_time,
                "airlines": airlines_count,
            }
            new_segments = segments + [segment]
            new_path = path + [nxt]
            if len(new_path) - 2 > max_stops:
                continue
            heapq.heappush(
                heap,
                (
                    new_total_time,
                    new_total_distance,
                    new_total_co2,
                    new_path,
                    new_segments,
                    new_layovers,
                ),
            )

    return None


def _compute_route_detail(origin, dest, airports, direct_routes, inbound_routes):
    cache_key = (origin, dest)
    cached = _ROUTE_DETAIL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if origin == dest:
        detail = {
            "availability": "same",
            "legs": 0,
            "stops": 0,
            "path": [origin],
            "segments": [],
            "distance": 0.0,
            "time": 0.0,
            "co2": 0.0,
            "airlines": 0,
        }
        _ROUTE_DETAIL_CACHE[cache_key] = detail
        return detail

    origin_data = airports.get(origin)
    dest_data = airports.get(dest)
    if not origin_data or not dest_data:
        detail = _fallback_route(origin, dest, airports)
        _ROUTE_DETAIL_CACHE[cache_key] = detail
        return detail

    direct_info = direct_routes.get(origin, {}).get(dest)
    if direct_info:
        dist = HaversineDistance(origin_data["lat"], origin_data["lon"], dest_data["lat"], dest_data["lon"])
        time = CalculateTime(dist)
        co2 = CalculateCO2Emissions(dist)
        airlines = len(direct_info.get("airlines", ())) if direct_info.get("airlines") else 0
        detail = {
            "availability": "direct",
            "legs": 1,
            "stops": 0,
            "path": [origin, dest],
            "segments": [
                {"from": origin, "to": dest, "distance": dist, "time": time, "airlines": airlines},
            ],
            "distance": dist,
            "time": time,
            "co2": co2,
            "airlines": airlines,
            "layover_minutes": 0.0,
        }
        _ROUTE_DETAIL_CACHE[cache_key] = detail
        return detail

    multi_stop = _search_best_route(origin, dest, airports, direct_routes, inbound_routes, _MAX_ALLOWED_STOPS)
    if multi_stop:
        _ROUTE_DETAIL_CACHE[cache_key] = multi_stop
        return multi_stop

    detail = _fallback_route(origin, dest, airports)
    _ROUTE_DETAIL_CACHE[cache_key] = detail
    return detail


def EvaluateCandidatesRouteAware(airportCodes, airports, routes_direct, routes_inbound):
    total_origins = len(airportCodes)
    candidate_entries = []

    candidate_codes = _select_candidate_codes(airportCodes, airports, routes_direct)

    for cand_code in candidate_codes:
        cand_data = airports.get(cand_code)
        if not cand_data:
            continue
        total_distance = 0.0
        total_time = 0.0
        total_co2 = 0.0
        stats_counts = {
            "direct": 0,
            "one_stop": 0,
            "two_stop": 0,
            "fallback": 0,
            "same": 0,
        }
        direct_airlines_sum = 0
        direct_airlines_count = 0
        candidate_routes = {}

        for origin_code in airportCodes:
            detail = _compute_route_detail(origin_code, cand_code, airports, routes_direct, routes_inbound)
            candidate_routes[origin_code] = detail
            total_distance += detail["distance"]
            total_time += detail["time"]
            total_co2 += detail["co2"]

            availability = detail["availability"]
            stats_counts[availability] = stats_counts.get(availability, 0) + 1

            if availability == "direct" and detail.get("airlines"):
                direct_airlines_sum += detail["airlines"]
                direct_airlines_count += 1

        avg_distance = total_distance / total_origins if total_origins else 0.0
        avg_time = total_time / total_origins if total_origins else 0.0
        score = 1 - (avg_distance / 15000.0)
        connectivity_penalty = 0.0
        if total_origins:
            connectivity_penalty += 0.04 * (stats_counts.get("one_stop", 0) / total_origins)
            connectivity_penalty += 0.08 * (stats_counts.get("two_stop", 0) / total_origins)
            connectivity_penalty += 0.16 * (stats_counts.get("fallback", 0) / total_origins)
        score -= connectivity_penalty
        if score < 0:
            score = 0.0
        elif score > 1:
            score = 1.0

        connectivity_summary = _format_connectivity_summary(stats_counts)
        avg_airlines = (direct_airlines_sum / direct_airlines_count) if direct_airlines_count else 0.0

        row = [
            cand_code,
            cand_data["name"],
            round(score, 3),
            round(avg_time, 3),
            round(total_co2, 3),
            round(total_distance, 3),
            connectivity_summary,
        ]

        candidate_entries.append(
            {
                "row": row,
                "detail": {
                    "stats": stats_counts.copy(),
                    "routes": candidate_routes,
                    "avg_airlines": round(avg_airlines, 3),
                    "connectivity_summary": connectivity_summary,
                    "aggregates": {
                        "score": score,
                        "mean_time": avg_time,
                        "total_co2": total_co2,
                        "total_distance": total_distance,
                        "penalty": connectivity_penalty,
                    },
                },
            }
        )

    candidate_entries.sort(key=lambda item: (-item["row"][2], item["row"][5], item["row"][3]))
    rows = [item["row"] for item in candidate_entries]
    meta = {
        "by_candidate": {item["row"][0]: item["detail"] for item in candidate_entries[:10]},
        "requested_origins": list(airportCodes),
        "ordered_candidates": [item["row"][0] for item in candidate_entries[:10]],
    }
    return rows, meta


def EvaluateCandidatesFixed(airportCodes, airports):
    routes_direct, routes_inbound = _get_routes()
    rows, _ = EvaluateCandidatesRouteAware(airportCodes, airports, routes_direct, routes_inbound)
    return rows


def EvaluateCandidates(airportCodes, airports):
    return EvaluateCandidatesFixed(airportCodes, airports)


def get_last_results_meta():
    return _LAST_RESULTS_META
