from pathlib import Path

INPUT_FILE = "data/etf_prices_converted.csv"
OUTPUT_FILE = "data/etf_prices_clean.csv"

# Read raw bytes
raw = Path(INPUT_FILE).read_bytes()

# Decode safely (removes invalid UTF-8 bytes)
clean_text = raw.decode("utf-8", errors="ignore")

# Write clean UTF-8 file
Path(OUTPUT_FILE).write_text(clean_text, encoding="utf-8")

print(f"✅ Clean UTF-8 file written to: {OUTPUT_FILE}")
