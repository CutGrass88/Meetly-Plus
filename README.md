# DurHack 2025 Project — Meetly+

This is our project for **DurHack 2025**, Durham University’s annual hackathon.  
It was built in under 24 hours using **Python** and aims to make global meetups **fairer and greener** by finding the most balanced meeting hub for people travelling from different locations.

---

## Overview

**Meetly+** helps distributed teams find the fairest meeting location by balancing travel time, total distance, and estimated CO₂ emissions.  
Users can input 2–25 IATA airport codes, and the app visualises all routes on a real-world map while ranking potential meeting hubs based on fairness and sustainability.

An integrated **AI component (Gemini API)** generates natural-language summaries explaining why a particular hub was chosen — making the results easy to interpret.

On average, the system takes **around 1 minute and 10 seconds** to calculate and generate all route data, fairness scores, and AI explanations.

---

## Features

- Interactive world map showing flight paths between airports  
- Input system supporting multiple origin airports  
- Fairness-based ranking of potential meeting hubs  
- AI-generated explanations using Google’s Gemini 2.0 Flash  
- Clean, dark-themed interface built with CustomTkinter  
- Dynamic data table showing travel metrics (time, distance, CO₂)
- Average runtime: ~1 min 10 sec for full analysis

---

## Tech Stack

- **Language:** Python  
- **Frameworks/Libraries:**  
  - `customtkinter` — modern GUI framework  
  - `tkintermapview` — interactive map visualisation  
  - `google-genai` — Gemini API for AI explanations  
  - `ttk` — data table styling  
- **Tools:** GitHub, VS Code, Google Gemini API
- **Data:** Openflights.com routs and airports data

---

## How to Run

1. Clone the repository:
   ```bash
   git clone https://github.com/SamsSide/durhack-2025-v2
   ```
2. Go into the project folder:
   ```bash
   cd durhack-2025-v2
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   python main.py
   ```

---

## Team

- **Sam Makin**
- **Justin Basson** 
- **Denis Ivanciuc**