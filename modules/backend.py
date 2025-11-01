import os

path = "durhack-2025/assets/airports.dat"
_AIRPORT_CACHE = None
numOrigins = 25

def LoadAirportData(path):
    airports = {}
    import csv
    with open(path, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        for parts in reader:
            ## Skip incomplete or invalid lines
            if len(parts) < 8:
                continue
            iata = parts[4].strip()
            if not iata or parts[6] == "" or parts[7] == "":
                continue

            try:
                lat = float(parts[6])
                lon = float(parts[7])
            except ValueError:
                continue  ## skip malformed coordinates

            airports[iata] = {
                "lat": lat,
                "lon": lon,
                "name": parts[1],
                "country": parts[3]
            }
    return airports
    
def _assets_path():
    try:
        root = os.path.dirname(os.path.dirname(__file__))
    except Exception:
        root = os.getcwd()
    return os.path.join(root, "assets", "airports.dat")

def _get_airports():
    global _AIRPORT_CACHE
    if _AIRPORT_CACHE is None:
        _AIRPORT_CACHE = LoadAirportData(_assets_path())
    return _AIRPORT_CACHE

def compute_top10(airportCodes):
    """Compute top 10 meeting candidates for given origin IATA codes.

    Returns a list of rows:
    [Meeting place (IATA), airport name, score, mean time (min), total CO2 (kg), total distance (km)]
    """
    airports = _get_airports()
    validated = ValidateOrigins(airportCodes, airports)
    if not validated:
        return []
    results = EvaluateCandidatesFixed(validated, airports)
    return results[:10]

def ValidateOrigins(airportCodes, airports): ## Validates user inputted airport codes
    origins = len(airportCodes)
    if (origins > numOrigins  or origins < 2):
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

def HaversineDistance(lat1, lon1, lat2, lon2): ## Calculates distance between two lat/lon points
    from math import radians, sin, cos, sqrt, atan2

    R = 6371.0  # Radius of the Earth in kilometers

    lat1_rad = radians(float(lat1))
    lon1_rad = radians(float(lon1))
    lat2_rad = radians(float(lat2))
    lon2_rad = radians(float(lon2))

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance

def CalculateTime(distance):
    cruiseSpeed = 875  # speed in km/h
    if distance <= 1e-6:
        return 0.0
    return 40 + ((distance * 60) / cruiseSpeed)  # time in minutes

def CalculateCO2Emissions(distance):
    emissionsFactor =  115 / 1000  # convert g to kg
    emissions = distance * emissionsFactor  # emissions in kg
    return emissions

def EvaluateCandidatesFixed(airportCodes, airports):
    """Improved evaluation that handles duplicate origins gracefully and
    ensures zero-time for same-airport attendees.

    Returns rows of [IATA, score, mean_time(min), total_co2(kg), total_distance(km)]
    """
    rows = []

    for cand_code, cand_data in airports.items():
        cand_lat, cand_lon = cand_data["lat"], cand_data["lon"]
        total_distance = 0.0
        total_time = 0.0
        total_co2 = 0.0

        for origin_code in airportCodes:
            o = airports[origin_code]
            dist = HaversineDistance(o["lat"], o["lon"], cand_lat, cand_lon)
            total_distance += dist
            total_time += CalculateTime(dist)
            total_co2 += CalculateCO2Emissions(dist)

        avg_dist = total_distance / len(airportCodes)
        avg_time = total_time / len(airportCodes)

        raw_score = 1 - (avg_dist / 15000.0)
        if raw_score < 0:
            raw_score = 0.0
        if raw_score > 1:
            raw_score = 1.0

        rows.append([cand_code, cand_data["name"], raw_score, avg_time, total_co2, total_distance])

    # Sort by: score desc, total_distance asc, avg_time asc
    rows.sort(key=lambda r: (-r[2], r[5], r[3]))

    results = [
        [iata, name, round(score, 3), round(mean_t, 3), round(co2, 3), round(dist, 3)]
        for (iata, name, score, mean_t, co2, dist) in rows
    ]
    return results

def EvaluateCandidates(airportCodes, airports):  ## Produces 2D array of results
    results = []

    for cand_code, cand_data in airports.items():
        cand_lat, cand_lon = cand_data["lat"], cand_data["lon"]
        total_distance = 0
        total_time = 0
        total_co2 = 0

        for origin_code in airportCodes:
            orig_data = airports[origin_code]
            dist = HaversineDistance(
                orig_data["lat"], orig_data["lon"],
                cand_lat, cand_lon
            )
            total_distance += dist
            total_time += CalculateTime(dist)
            total_co2 += CalculateCO2Emissions(dist)

        avg_time = total_time / len(airportCodes)
        score = 1 - ((total_distance / len(airportCodes)) / 15000)
        score = round(max(min(score, 1), 0), 3)

        results.append([
            cand_code,                       ## IATA
            cand_data["name"],
            score,                            ## 0–1 score
            round(avg_time, 3),               ## mean flight time (min)
            round(total_co2, 3),              ## total CO₂ (kg)
            round(total_distance, 3)          ## total distance (km)
        ])

    results.sort(key=lambda x: x[2], reverse=True)
    return results





