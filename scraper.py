import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from tqdm import tqdm

BASE = "https://results.eci.gov.in/ResultAcGenNov2025/"
OUTPUT_CSV = "2025_Bihar_Election_Fulldata.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://results.eci.gov.in/",
}

def safe_float(x):
    if not x:
        return 0.0
    x = str(x).replace(",", "").strip()
    x = re.sub(r"[^\d.\-]", "", x)
    try:
        return float(x)
    except:
        return 0.0

def find_candidate_table(soup):
    tables = soup.find_all("table")
    for t in tables:
        header = " ".join([th.get_text(" ", strip=True).lower() for th in t.find_all("th")])
        if "candidate" in header and "total" in header:
            return t
    return None

def extract_constituency_name(soup):
    """
    Extract constituency name from heading such as:
    "Constituency: 195 Maner"
    """
    h2_tag = soup.find("h2")
    if h2_tag:
        text = h2_tag.get_text(" ", strip=True)
        text = text.replace("Constituency:", "").strip()
        # example: "195 Maner" → remove the number to extract name
        name1 = re.sub(r"^\d+\s*", "", text).strip()
        name=name1.split('-',1)[1].split('(',1)[0].strip().title()
        return name

    # fallback search in case HTML structure differs
    possible = soup.find(string=re.compile("Constituency", re.I))
    if possible:
        text = possible.get_text(" ", strip=True)
        text = text.replace("Constituency:", "").strip()
        name1 = re.sub(r"^\d+\s*", "", text).strip()
        name=name1.split('-',1)[1].split('(',1)[0].strip().title()
        return name

    return ""

def scrape_constituency(ac_no, session):
    url = f"{BASE}ConstituencywiseS04{ac_no:01}.htm"

    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            print(f"AC {ac_no} → HTTP {r.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching AC {ac_no}:", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    # Extract Constituency Name
    ac_name = extract_constituency_name(soup)

    table = find_candidate_table(soup)
    if table is None:
        print(f"No candidate table found for AC {ac_no}")
        return []

    rows = table.find_all("tr")
    header = [th.get_text(" ", strip=True).lower() for th in rows[0].find_all("th")]

    def col_index(names):
        for i, h in enumerate(header):
            for n in names:
                if n in h:
                    return i
        return None

    idx_cand = col_index(["candidate"])
    idx_party = col_index(["party"])
    idx_evm = col_index(["evm"])
    idx_postal = col_index(["postal"])
    idx_total = col_index(["total"])
    idx_pct = col_index(["%", "share"])

    data = []

    for row in rows[1:]:
        cols = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        if len(cols) < 2:
            continue

        data.append({
            "AC_No": ac_no,
            "AC_Name": ac_name,   # NEW FIELD
            "Candidate": cols[idx_cand] if idx_cand is not None else "",
            "Party": cols[idx_party] if idx_party is not None else "",
            "EVM_Votes": safe_float(cols[idx_evm] if idx_evm is not None else ""),
            "Postal_Votes": safe_float(cols[idx_postal] if idx_postal is not None else ""),
            "Total_Votes": safe_float(cols[idx_total] if idx_total is not None else ""),
            "Vote_Share_%": safe_float(cols[idx_pct] if idx_pct is not None else ""),
            "Source_URL": url
        })

    return data

def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    all_data = []

    print("Scraping Bihar 2025 results with constituency names...\n")

    for ac in tqdm(range(1, 244)):  # Bihar AC 1 → 243
        rows = scrape_constituency(ac, session)
        if rows:
            all_data.extend(rows)
        time.sleep(0.5)

    df = pd.DataFrame(all_data)

    if df.empty:
        print("No data collected!")
        return

    df.loc[df["Total_Votes"] == 0, "Total_Votes"] = df["EVM_Votes"] + df["Postal_Votes"]

    df["Rank_In_Constituency"] = df.groupby("AC_No")["Total_Votes"] \
        .rank(method="dense", ascending=False).astype(int)

    df = df.sort_values(["AC_No", "Rank_In_Constituency"])

    df.to_csv(OUTPUT_CSV, index=False)

    print(f"\nCSV saved → {OUTPUT_CSV}")
    print(f"Rows collected: {len(df)}")

if __name__ == "__main__":
    main()
