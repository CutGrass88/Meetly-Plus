from collections import Counter
from google import genai

client = genai.Client(api_key="AIzaSyBHdGOr2dWxUcwEQMQ4xmJX3aRKUVgEbP0")

def reason(CO2, time, distance, numPeople, locations, hub, connectivity=None, stats=None):
    counts = Counter([str(item).upper() for item in (locations or [])])
    origin_summary = ", ".join(f"{code} x{count}" for code, count in counts.items()) if counts else "None"
    duplicate_note = "Yes" if any(count > 1 for count in counts.values()) else "No"

    if isinstance(stats, dict):
        stats_line = ", ".join(
            [
                f"direct {stats.get('direct', 0)}",
                f"one-stop {stats.get('one_stop', 0)}",
                f"two-stop {stats.get('two_stop', 0)}",
                f"three-stop {stats.get('three_stop', 0)}",
                f"fallback {stats.get('fallback', 0)}",
                f"local {stats.get('same', 0)}",
            ]
        )
    else:
        stats_line = "No detailed route mix provided"

    connectivity_summary = connectivity or "Connectivity data unavailable"

    fallback = (
        f"{hub} is the leading option for {numPeople} attendees (origins: {origin_summary}). "
        f"Average travel time is about {time:.2f} minutes with total distance {distance:.2f} km "
        f"and emissions {CO2:.2f} kg CO2. Shared departures detected: {duplicate_note}. "
        f"Connectivity snapshot: {connectivity_summary}. Route mix: {stats_line}. "
        f"This recommendation balances travel effort and environmental impact across the group."
    )

    prompt = f"""
You are an AI assistant that explains meeting hub recommendations clearly and concisely.

Inputs:
- Proposed meeting hub: {hub}
- Starting locations (with counts): {origin_summary}
- Multiple attendees share a starting airport: {duplicate_note}
- Number of attendees: {numPeople}
- Total CO2 emitted: {CO2:.2f} kg
- Average travel time: {time:.2f} minutes
- Average travel distance: {distance:.2f} km
- Connectivity summary (direct vs connections): {connectivity_summary}
- Route mix counts: {stats_line}

Task:
Write a short summary (2-3 sentences) explaining why this location is a good meeting hub for these attendees.
Explicitly consider if some attendees share the same origin (for example, zero or minimal travel for those already at the hub) and how that affects fairness and total impact.
Keep the tone informative, concise, and suitable for a dashboard summary. Avoid restating all numeric inputs; focus on insights.
Use the data provided to craft your explanation and use the data in your reasoning.
Say the name of the airport hub at the start of your response along with the country it is located in.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = getattr(response, "text", None)
        if text and str(text).strip():
            return text.strip()
    except Exception:
        pass

    return fallback
