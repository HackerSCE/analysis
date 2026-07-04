SECTOR_FILTERS = [
    "IT",
    "Pharma",
    "Banking",
    "Financial Services",
    "Auto",
    "FMCG",
    "Metal",
    "Energy",
    "PSU",
    "Realty",
    "Telecom",
    "Media",
    "Infrastructure",
    "Chemicals",
    "Capital Goods",
    "Healthcare",
    "Consumer Durable",
    "All Sectors",
]


SECTOR_MAP = {
    "ABB": ["Capital Goods"],
    "ABCAPITAL": ["Financial Services"],
    "ABFRL": ["Consumer Durable"],
    "ACC": ["Infrastructure"],
    "ADANIENSOL": ["Energy", "Infrastructure"],
    "ADANIENT": ["Infrastructure"],
    "ADANIGREEN": ["Energy"],
    "ADANIPORTS": ["Infrastructure"],
    "ALKEM": ["Pharma", "Healthcare"],
    "AMBUJACEM": ["Infrastructure"],
    "ANGELONE": ["Financial Services"],
    "APLAPOLLO": ["Metal", "Capital Goods"],
    "APOLLOHOSP": ["Healthcare"],
    "APOLLOTYRE": ["Auto"],
    "ASHOKLEY": ["Auto"],
    "ASIANPAINT": ["Consumer Durable"],
    "ASTRAL": ["Capital Goods"],
    "ATGL": ["Energy"],
    "AUBANK": ["Banking", "Financial Services"],
    "AUROPHARMA": ["Pharma", "Healthcare"],
    "AXISBANK": ["Banking", "Financial Services"],
    "BAJAJ-AUTO": ["Auto"],
    "BAJAJFINSV": ["Financial Services"],
    "BAJFINANCE": ["Financial Services"],
    "BALKRISIND": ["Auto"],
    "BANDHANBNK": ["Banking", "Financial Services"],
    "BANKBARODA": ["Banking", "Financial Services", "PSU"],
    "BANKINDIA": ["Banking", "Financial Services", "PSU"],
    "BATAINDIA": ["Consumer Durable"],
    "BEL": ["Capital Goods", "PSU"],
    "BERGEPAINT": ["Consumer Durable"],
    "BHARATFORG": ["Auto", "Capital Goods"],
    "BHARTIARTL": ["Telecom"],
    "BHEL": ["Capital Goods", "PSU"],
    "BIOCON": ["Pharma", "Healthcare"],
    "BOSCHLTD": ["Auto"],
    "BPCL": ["Energy", "PSU"],
    "BRITANNIA": ["FMCG"],
    "BSE": ["Financial Services"],
    "BSOFT": ["IT"],
    "CAMS": ["Financial Services"],
    "CANBK": ["Banking", "Financial Services", "PSU"],
    "CDSL": ["Financial Services"],
    "CESC": ["Energy"],
    "CGPOWER": ["Capital Goods", "Energy"],
    "CHAMBLFERT": ["Chemicals"],
    "CHOLAFIN": ["Financial Services"],
    "CIPLA": ["Pharma", "Healthcare"],
    "COALINDIA": ["Energy", "Metal", "PSU"],
    "COFORGE": ["IT"],
    "COLPAL": ["FMCG"],
    "CONCOR": ["Infrastructure", "PSU"],
    "COROMANDEL": ["Chemicals"],
    "CROMPTON": ["Consumer Durable"],
    "CUB": ["Banking", "Financial Services"],
    "CUMMINSIND": ["Capital Goods"],
    "CYIENT": ["IT"],
    "DABUR": ["FMCG"],
    "DALBHARAT": ["Infrastructure"],
    "DEEPAKNTR": ["Chemicals"],
    "DELHIVERY": ["Infrastructure"],
    "DIVISLAB": ["Pharma", "Healthcare"],
    "DIXON": ["Consumer Durable"],
    "DLF": ["Realty"],
    "DMART": ["FMCG"],
    "DRREDDY": ["Pharma", "Healthcare"],
    "EICHERMOT": ["Auto"],
    "ESCORTS": ["Auto"],
    "EXIDEIND": ["Auto"],
    "FEDERALBNK": ["Banking", "Financial Services"],
    "FORTIS": ["Healthcare"],
    "GAIL": ["Energy", "PSU"],
    "GLENMARK": ["Pharma", "Healthcare"],
    "GMRINFRA": ["Infrastructure"],
    "GNFC": ["Chemicals", "PSU"],
    "GODREJCP": ["FMCG"],
    "GODREJPROP": ["Realty"],
    "GRANULES": ["Pharma", "Healthcare"],
    "GRASIM": ["Infrastructure"],
    "GUJGASLTD": ["Energy"],
    "HAL": ["Capital Goods", "PSU"],
    "HAVELLS": ["Consumer Durable", "Capital Goods"],
    "HCLTECH": ["IT"],
    "HDFCAMC": ["Financial Services"],
    "HDFCBANK": ["Banking", "Financial Services"],
    "HDFCLIFE": ["Financial Services"],
    "HEROMOTOCO": ["Auto"],
    "HFCL": ["Telecom"],
    "HINDALCO": ["Metal"],
    "HINDCOPPER": ["Metal", "PSU"],
    "HINDPETRO": ["Energy", "PSU"],
    "HINDUNILVR": ["FMCG"],
    "HUDCO": ["Financial Services", "PSU", "Infrastructure"],
    "ICICIBANK": ["Banking", "Financial Services"],
    "ICICIGI": ["Financial Services"],
    "ICICIPRULI": ["Financial Services"],
    "IDEA": ["Telecom"],
    "IDFCFIRSTB": ["Banking", "Financial Services"],
    "IEX": ["Energy", "Financial Services"],
    "IGL": ["Energy"],
    "INDHOTEL": ["FMCG"],
    "INDIANB": ["Banking", "Financial Services", "PSU"],
    "INDIGO": ["Infrastructure"],
    "INDUSINDBK": ["Banking", "Financial Services"],
    "INDUSTOWER": ["Telecom"],
    "INFY": ["IT"],
    "IOC": ["Energy", "PSU"],
    "IPCALAB": ["Pharma", "Healthcare"],
    "IRB": ["Infrastructure"],
    "IRCTC": ["Infrastructure", "PSU"],
    "IREDA": ["Financial Services", "Energy", "PSU"],
    "IRFC": ["Financial Services", "PSU", "Infrastructure"],
    "ITC": ["FMCG"],
    "JINDALSTEL": ["Metal"],
    "JIOFIN": ["Financial Services"],
    "JSWENERGY": ["Energy"],
    "JSWSTEEL": ["Metal"],
    "JUBLFOOD": ["FMCG"],
    "KALYANKJIL": ["Consumer Durable"],
    "KEI": ["Capital Goods"],
    "KOTAKBANK": ["Banking", "Financial Services"],
    "KPITTECH": ["IT"],
    "LALPATHLAB": ["Healthcare"],
    "LAURUSLABS": ["Pharma", "Healthcare"],
    "LICHSGFIN": ["Financial Services"],
    "LICI": ["Financial Services", "PSU"],
    "LODHA": ["Realty"],
    "LT": ["Capital Goods", "Infrastructure"],
    "LTIM": ["IT"],
    "LTTS": ["IT"],
    "LUPIN": ["Pharma", "Healthcare"],
    "M&M": ["Auto"],
    "M&MFIN": ["Financial Services", "Auto"],
    "MANAPPURAM": ["Financial Services"],
    "MARICO": ["FMCG"],
    "MARUTI": ["Auto"],
    "MAXHEALTH": ["Healthcare"],
    "MCX": ["Financial Services"],
    "MFSL": ["Financial Services"],
    "MGL": ["Energy"],
    "MOTHERSON": ["Auto"],
    "MPHASIS": ["IT"],
    "MRF": ["Auto"],
    "MUTHOOTFIN": ["Financial Services"],
    "NATIONALUM": ["Metal", "PSU"],
    "NAUKRI": ["IT"],
    "NAVINFLUOR": ["Chemicals"],
    "NBCC": ["Infrastructure", "PSU"],
    "NCC": ["Infrastructure"],
    "NESTLEIND": ["FMCG"],
    "NHPC": ["Energy", "PSU"],
    "NMDC": ["Metal", "PSU"],
    "NTPC": ["Energy", "PSU"],
    "OBEROIRLTY": ["Realty"],
    "OFSS": ["IT"],
    "OIL": ["Energy", "PSU"],
    "ONGC": ["Energy", "PSU"],
    "PAGEIND": ["Consumer Durable"],
    "PATANJALI": ["FMCG"],
    "PAYTM": ["Financial Services", "IT"],
    "PEL": ["Financial Services"],
    "PERSISTENT": ["IT"],
    "PETRONET": ["Energy"],
    "PFC": ["Financial Services", "Energy", "PSU"],
    "PHOENIXLTD": ["Realty"],
    "PIDILITIND": ["Chemicals", "Consumer Durable"],
    "PIIND": ["Chemicals"],
    "PNB": ["Banking", "Financial Services", "PSU"],
    "POLYCAB": ["Capital Goods", "Consumer Durable"],
    "POWERGRID": ["Energy", "PSU"],
    "PPLPHARMA": ["Pharma", "Healthcare"],
    "PRESTIGE": ["Realty"],
    "RAMCOCEM": ["Infrastructure"],
    "RBLBANK": ["Banking", "Financial Services"],
    "RECLTD": ["Financial Services", "Energy", "PSU"],
    "RELIANCE": ["Energy", "FMCG"],
    "SAIL": ["Metal", "PSU"],
    "SBICARD": ["Financial Services", "PSU"],
    "SBILIFE": ["Financial Services"],
    "SBIN": ["Banking", "Financial Services", "PSU"],
    "SHREECEM": ["Infrastructure"],
    "SHRIRAMFIN": ["Financial Services"],
    "SIEMENS": ["Capital Goods"],
    "SJVN": ["Energy", "PSU"],
    "SRF": ["Chemicals"],
    "SUNPHARMA": ["Pharma", "Healthcare"],
    "SUNTV": ["Media"],
    "SUPREMEIND": ["Capital Goods"],
    "SYNGENE": ["Pharma", "Healthcare"],
    "TATACHEM": ["Chemicals"],
    "TATACOMM": ["Telecom"],
    "TATACONSUM": ["FMCG"],
    "TATAELXSI": ["IT"],
    "TATAMOTORS": ["Auto"],
    "TATAPOWER": ["Energy"],
    "TATASTEEL": ["Metal"],
    "TCS": ["IT"],
    "TECHM": ["IT"],
    "TIINDIA": ["Auto", "Capital Goods"],
    "TITAN": ["Consumer Durable"],
    "TORNTPHARM": ["Pharma", "Healthcare"],
    "TORNTPOWER": ["Energy"],
    "TRENT": ["Consumer Durable"],
    "TVSMOTOR": ["Auto"],
    "UBL": ["FMCG"],
    "ULTRACEMCO": ["Infrastructure"],
    "UNIONBANK": ["Banking", "Financial Services", "PSU"],
    "UNITDSPR": ["FMCG"],
    "UPL": ["Chemicals"],
    "VBL": ["FMCG"],
    "VEDL": ["Metal", "Energy"],
    "VOLTAS": ["Consumer Durable"],
    "WIPRO": ["IT"],
    "YESBANK": ["Banking", "Financial Services"],
    "ZEEL": ["Media"],
    "ZYDUSLIFE": ["Pharma", "Healthcare"],
}


def clean_symbol(symbol):
    value = (symbol or "").upper().strip()
    if ":" in value:
        value = value.split(":", 1)[1]
    for suffix in ("-EQ", "-BE"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value


def sectors_for_symbol(symbol, stock_name=""):
    cleaned = clean_symbol(symbol)
    if cleaned in SECTOR_MAP:
        return SECTOR_MAP[cleaned]
    return infer_sector(cleaned, stock_name)


def display_sector(sectors):
    return " / ".join(sectors or ["Capital Goods"])


def infer_sector(symbol, stock_name=""):
    text = f"{symbol} {stock_name}".upper()
    if "BANK" in text:
        return ["Banking", "Financial Services"]
    if any(token in text for token in ("FIN", "CREDIT", "LIFE", "AMC", "INSUR", "SECURIT")):
        return ["Financial Services"]
    if any(token in text for token in ("PHARMA", "LAB", "HEALTH", "HOSP", "BIO")):
        return ["Pharma", "Healthcare"]
    if any(token in text for token in ("AUTO", "MOTOR", "TYRE", "FORG")):
        return ["Auto"]
    if any(token in text for token in ("STEEL", "METAL", "ALUM", "COPPER", "ZINC")):
        return ["Metal"]
    if any(token in text for token in ("POWER", "ENERGY", "OIL", "GAS", "PETRO", "COAL")):
        return ["Energy"]
    if any(token in text for token in ("REAL", "PROP", "REALTY")):
        return ["Realty"]
    if any(token in text for token in ("TEL", "COMM", "TOWER")):
        return ["Telecom"]
    if any(token in text for token in ("MEDIA", "TV", "CINEMA")):
        return ["Media"]
    if any(token in text for token in ("PORT", "INFRA", "CEMENT", "CONSTRUCT", "ROAD")):
        return ["Infrastructure"]
    if any(token in text for token in ("CHEM", "FERT", "FLUOR")):
        return ["Chemicals"]
    if any(token in text for token in ("TECH", "SOFT", "INFO", "SYSTEM")):
        return ["IT"]
    if any(token in text for token in ("FOOD", "CONSUM", "BEVER", "PAINT", "RETAIL")):
        return ["FMCG"]
    return ["Capital Goods"]
