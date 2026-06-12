import requests
import pandas as pd
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup


HISTORICAL_CSV = "water_reserves_old.csv"
OUTPUT_CSV = "water_reserves_latest.csv"
LATEST_DAY_COMPARE_CSV = "latest_day_compare.csv"


def fetch_eydap_reservoir_rss() -> pd.DataFrame:
    """
    Fetch extractable reservoir stock data from EYDAP RSS feed.
    Covers: Εύηνος, Μαραθώνας, Μόρνος, Υλίκη — updated daily, last 31 days.
    """
    url = "https://www.eydap.gr/handlers/rss.ashx?collection=WaterProduction&Culture=69"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()

    root = ET.fromstring(response.content)
    description_html = root.find(".//item/description").text

    soup = BeautifulSoup(description_html, "html.parser")
    table = soup.find("table")

    headers, rows = None, []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
        if headers is None:
            headers = cells
        else:
            rows.append(cells)

    df = pd.DataFrame(rows, columns=headers)

    df = df.rename(columns={
        "ΗΜΕΡΟΜΗΝΙΑ": "Date",
        "ΕΥΗΝΟΣ": "Eyinos",
        "ΜΑΡΑΘΩΝΑΣ": "Marathonas",
        "ΜΟΡΝΟΣ": "Mornos",
        "ΥΛΙΚΗ": "Yliki",
        "ΣΥΝΟΛΟ": "Synolo",
        "TOTAL": "Total",
    })

    df["Date"] = pd.to_datetime(df["Date"].str.strip(), format="%d/%m/%Y")

    numeric_cols = ["Eyinos", "Marathonas", "Mornos", "Yliki", "Synolo", "Total"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .astype(float)
                .astype(int)
            )

    if "Total" in df.columns:
        df = df.drop(columns=["Total"])
    
    df = df.rename(columns={"Synolo": "Total"})
  
    return df.reset_index(drop=True)


def load_historical_data(path: str) -> pd.DataFrame:
    df1 = pd.read_csv(path)

    df1 = df1.rename(columns={
        "date": "Date"
    })

    expected_cols = ["Date", "Eyinos", "Marathonas", "Mornos", "Yliki", "Total"]
    missing = [col for col in expected_cols if col not in df1.columns]
    if missing:
        raise ValueError(f"Missing expected columns in historical file: {missing}")

    df1 = df1[expected_cols].copy()
    df1["Date"] = pd.to_datetime(df1["Date"], errors="coerce")

    numeric_cols = ["Eyinos", "Marathonas", "Mornos", "Yliki", "Total"]
    for col in numeric_cols:
        df1[col] = pd.to_numeric(df1[col], errors="coerce")

    df1 = df1.dropna(subset=["Date"])
    return df1.reset_index(drop=True)


def build_latest_dataset(historical_path: str, output_csv: str) -> pd.DataFrame:
    df_historical = load_historical_data(historical_path)
    df_latest = fetch_eydap_reservoir_rss()

    combined = pd.concat([df_historical, df_latest], ignore_index=True)

    duplicate_rows = (
        combined[combined.duplicated(subset=["Date"], keep=False)]
        .sort_values("Date")
        .reset_index(drop=True)
    )

    if not duplicate_rows.empty:
        print("Duplicate dates found:")
        print(duplicate_rows[["Date", "Eyinos", "Marathonas", "Mornos", "Yliki", "Total"]])

    df_clean = (
        combined
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )

    df_clean.to_csv(output_csv, index=False)

    print(f"\nSaved cleaned file to: {output_csv}")
    print(f"Rows in historical file: {len(df_historical):,}")
    print(f"Rows fetched from RSS: {len(df_latest):,}")
    print(f"Rows after deduplication: {len(df_clean):,}")
    print(f"Latest date: {df_clean['Date'].max().date()}")
    print(f"Latest total reserves: {df_clean.loc[df_clean['Date'].idxmax(), 'Total']:,} m³")

    return df_clean

# Compare dates
def build_latest_day_compare(df: pd.DataFrame, output_csv: str) -> pd.DataFrame:
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

    latest_date = df["Date"].max()
    latest_month = latest_date.month
    latest_day = latest_date.day

    compare_df = (
        df[
            (df["Date"].dt.month == latest_month) &
            (df["Date"].dt.day == latest_day)
        ]
        .sort_values("Date")
        .reset_index(drop=True)
    )

    compare_df.to_csv(output_csv, index=False, date_format="%Y-%m-%d")

    print(f"\nSaved latest-day comparison file to: {output_csv}")
    print(f"Latest date used for comparison: {latest_date.date()}")
    print(f"Rows in comparison file: {len(compare_df):,}")

    return compare_df


# Execute dataset retrieve and update
df = build_latest_dataset(HISTORICAL_CSV, OUTPUT_CSV)

# Execute data comparison
latest_day_compare = build_latest_day_compare(df, LATEST_DAY_COMPARE_CSV)

print(df.tail(10))
print(latest_day_compare.tail(10))
