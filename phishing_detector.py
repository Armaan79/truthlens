"""Phishing URL detection: Random Forest model + offline domain intelligence.

HTTPS no longer proves a site is safe (most phishing sites have certificates),
so the verdict is driven by WHO owns the domain:
  - official brand domains (allowlist)       -> strong legitimate signal
  - brand names on a domain they don't own   -> impersonation
  - look-alike spellings (paypa1, rnicrosoft) -> typosquatting
  - free hosting, risky TLDs, punycode, IPs, redirects, random-looking names
The Random Forest (13 URL-shape features, unchanged so the saved model still
works) is blended in as a second opinion. Everything runs offline - no APIs.
"""
from urllib.parse import urlparse, unquote, parse_qs
import ipaddress
import math
import re
import joblib
import os

# Load relative to this file so the app also starts from another folder (e.g. VS Code).
model=joblib.load(os.path.join(os.path.dirname(os.path.abspath(__file__)),"model","phishing_model.pkl"))

SUSPICIOUS_WORDS=[
    "login","verify","update","secure","account","password",
    "signin","confirm","wallet","bank","payment","billing",
    "recover","unlock","credential","kyc","refund","reward","suspend",
    "otp","ekyc","validate","authenticate","unblock","redeem"
]

SHORTENERS={"bit.ly","tinyurl.com","t.co","goo.gl","is.gd","ow.ly","buff.ly","cutt.ly",
            "rb.gy","shorturl.at","tiny.cc","rebrand.ly","t.ly","s.id","v.gd","bitly.com"}

# Brand -> domains it really owns. A brand name anywhere else is impersonation.
BRANDS={
    "google":["google.com","google.co.in","youtube.com","gmail.com","googleusercontent.com"],
    "gmail":["gmail.com","google.com"],"youtube":["youtube.com","youtu.be","google.com"],
    "microsoft":["microsoft.com","live.com","outlook.com","office.com","microsoftonline.com","bing.com","azure.com"],
    "office365":["office.com","microsoft.com","microsoftonline.com"],"outlook":["outlook.com","live.com","office.com"],
    "microsoftonline":["microsoftonline.com"],"apple":["apple.com","icloud.com"],"icloud":["icloud.com","apple.com"],
    "amazon":["amazon.com","amazon.in","amazon.co.uk","amazon.jobs","amazonaws.com","primevideo.com","amazonpay.in"],
    "paypal":["paypal.com","paypal.me"],"netflix":["netflix.com"],
    "facebook":["facebook.com","fb.com","meta.com"],"instagram":["instagram.com"],
    "whatsapp":["whatsapp.com","whatsapp.net"],"linkedin":["linkedin.com"],
    "twitter":["twitter.com","x.com"],"dropbox":["dropbox.com"],"docusign":["docusign.com","docusign.net"],
    "yahoo":["yahoo.com"],"github":["github.com","github.io"],"adobe":["adobe.com"],
    "flipkart":["flipkart.com"],"myntra":["myntra.com"],"paytm":["paytm.com","paytmbank.com"],
    "phonepe":["phonepe.com"],"gpay":["google.com"],"sbi":["onlinesbi.sbi","sbi.co.in","sbicard.com","onlinesbi.com"],
    "onlinesbi":["onlinesbi.sbi","onlinesbi.com"],"hdfc":["hdfcbank.com","hdfc.com","hdfclife.com"],
    "hdfcbank":["hdfcbank.com"],"icici":["icicibank.com","icicidirect.com","iciciprulife.com"],
    "axisbank":["axisbank.com"],"kotak":["kotak.com"],"yesbank":["yesbank.in"],"pnb":["pnbindia.in"],
    "irctc":["irctc.co.in"],"uidai":["uidai.gov.in"],"aadhaar":["uidai.gov.in"],"incometax":["incometax.gov.in"],
    "epfo":["epfindia.gov.in"],"airtel":["airtel.in","airtel.com"],"jio":["jio.com"],
    "indiapost":["indiapost.gov.in"],"wellsfargo":["wellsfargo.com"],"chase":["chase.com"],
    "dhl":["dhl.com"],"fedex":["fedex.com"],"steam":["steampowered.com","steamcommunity.com"],
    "binance":["binance.com"],"coinbase":["coinbase.com"],"metamask":["metamask.io"],
    "swiggy":["swiggy.com","swiggy.in"],"zomato":["zomato.com"],"makemytrip":["makemytrip.com"],
    "bookmyshow":["bookmyshow.com"],"canva":["canva.com"],"spotify":["spotify.com"],"meesho":["meesho.com"],
    "ajio":["ajio.com"],"nykaa":["nykaa.com"],"bigbasket":["bigbasket.com"],"zerodha":["zerodha.com"],
    "groww":["groww.in"],"cred":["cred.club"],"bhim":["bhimupi.org.in","npci.org.in"],"yono":["onlinesbi.sbi","sbi.co.in"],
}
OFFICIAL={d for ds in BRANDS.values() for d in ds}

# Well-known sites with no brand rule above (not impersonated often, but common).
TRUSTED=OFFICIAL|{
    "wikipedia.org","stackoverflow.com","bbc.com","bbc.co.uk","reuters.com","thehindu.com","ndtv.com",
    "indiatimes.com","hindustantimes.com","indianexpress.com","zomato.com","swiggy.com","zoom.us",
    "slack.com","notion.so","reddit.com","quora.com","medium.com","cloudflare.com","mozilla.org",
    "python.org","w3schools.com","geeksforgeeks.org","coursera.org","udemy.com","spotify.com",
    "gov.in","nic.in","rbi.org.in","npci.org.in","makemytrip.com","bookmyshow.com","ola.com","uber.com",
}

# Free hosting / site builders: real platforms, but anyone can publish a page on them.
FREE_HOSTS={"web.app","firebaseapp.com","netlify.app","vercel.app","pages.dev","workers.dev","github.io",
            "glitch.me","herokuapp.com","onrender.com","azurewebsites.net","blogspot.com","weebly.com",
            "wixsite.com","000webhostapp.com","repl.co","ngrok.io","ngrok-free.app","r2.dev","framer.app",
            "webflow.io","square.site","godaddysites.com","sites.google.com","forms.gle","ipfs.io"}

RISKY_TLDS={"xyz","top","tk","ml","ga","cf","gq","click","buzz","rest","zip","mov","cam","icu","sbs",
            "cfd","monster","cyou","work","support","download","country","kim","men","loan","win",
            "bid","review","date","racing","party","stream","gdn","ru","su","kz","online","site","live"}

MULTI_SUFFIX={"co.in","gov.in","org.in","net.in","ac.in","nic.in","res.in","co.uk","org.uk","gov.uk",
              "ac.uk","com.au","net.au","co.jp","com.br","co.za","com.sg","com.my","co.nz"}

DANGEROUS_FILES=re.compile(r"\.(?:apk|exe|scr|msi|bat|cmd|vbs|jar|ps1|dmg|iso)(?:$|\?)",re.I)
HOMOGLYPHS=str.maketrans({"0":"o","1":"l","3":"e","4":"a","5":"s","7":"t","8":"b","@":"a","$":"s"})


def extract_features(url):
    """13 features the saved Random Forest was trained on - do not change."""
    p=urlparse(url)
    host=p.netloc.lower()
    return [
        len(url),len(host),url.count("."),url.count("-"),
        url.count("/"),url.count("@"),url.count("?"),url.count("="),
        url.count("%"),int(p.scheme!="https"),
        int(bool(re.search(r"\d+\.\d+\.\d+\.\d+",host))),
        int("@" in url),
        int(any(w in url.lower() for w in
            ["login","verify","update","secure","account","password"]))
    ]


# ---------- helpers ----------

def registered_domain(host):
    """paypal.com.verify.xyz -> verify.xyz ; retail.onlinesbi.sbi -> onlinesbi.sbi"""
    parts=host.strip(".").split(".")
    if len(parts)<=2:
        return host
    take=3 if ".".join(parts[-2:]) in MULTI_SUFFIX else 2
    return ".".join(parts[-take:])


def on_domain(host,domain):
    return host==domain or host.endswith("."+domain)


def is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        # decimal / hex IP tricks: http://3232235777 or http://0xC0A80101
        return bool(re.fullmatch(r"\d{8,10}|0x[0-9a-f]{8}",host))


def edit_distance(a,b):
    prev=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        cur=[i]
        for j,cb in enumerate(b,1):
            cur.append(min(prev[j]+1,cur[j-1]+1,prev[j-1]+(ca!=cb)))
        prev=cur
    return prev[-1]


def entropy(text):
    return -sum(text.count(c)/len(text)*math.log2(text.count(c)/len(text)) for c in set(text)) if text else 0


def lookalike(host):
    """Brand imitated by a misspelt/homoglyph word anywhere in the host:
    paypa1, rnicrosoft, faceb00k, linkedln, amaz0n, googl, amazonn."""
    words=set(re.split(r"[.-]",host))|{host.split(".")[0].replace("-","")}
    for word in words:
        norm=word.translate(HOMOGLYPHS).replace("rn","m").replace("vv","w")
        for brand in BRANDS:
            if len(brand)<5 or word==brand or len(word)<4:
                continue
            if norm==brand or norm.replace("l","i")==brand.replace("l","i"):
                return brand
            d=edit_distance(word,brand)
            # long brands: up to 2 edits; short brands only when truncated/extended (googl, amazonn),
            # so ordinary words like "apply" are not mistaken for "apple"
            if (len(brand)>=7 and d<=2 and abs(len(word)-len(brand))<=2) or \
               (d==1 and (brand.startswith(word) or (word.startswith(brand) and word[-1]==word[-2]))):
                return brand
    return None


# ---------- rule engine ----------

def security_check(url):
    """Return (risk 0-100, reasons, trust signals)."""
    p=urlparse(url)
    host=(p.hostname or "").lower().rstrip(".").removeprefix("www.")
    lower=unquote(url).lower()
    path=unquote(p.path+"?"+p.query).lower()
    reg=registered_domain(host)
    label=reg.split(".")[0]
    tld=host.rsplit(".",1)[-1] if "." in host else ""
    sub=host[:-len(reg)].rstrip(".") if host.endswith(reg) else ""
    reasons,good,risk=[],[],0

    def flag(points,why):
        nonlocal risk
        risk+=points
        reasons.append(why)

    if p.scheme not in ("http","https"):
        flag(60,f"Uses a dangerous '{p.scheme}:' link instead of a website address")
    if not host:
        return min(risk+40,100),reasons+["No valid website domain found"],good

    free_host=next((f for f in FREE_HOSTS if on_domain(host,f)),None)
    trusted=any(on_domain(host,d) for d in TRUSTED) and not free_host

    if trusted:
        good.append(f"Official domain: {reg}")
    if p.scheme=="https":
        good.append("Uses HTTPS (encrypted - but phishing sites use it too)")
    else:
        flag(10,"Does not use HTTPS")

    # --- impersonation: brand name on a domain the brand doesn't own ---
    owner_ok=lambda b:any(on_domain(host,d) for d in BRANDS[b])
    tokens=set(re.split(r"[^a-z0-9]+",host))
    in_host=[b for b in BRANDS if (b in tokens or (len(b)>=6 and b in host.replace("-",""))) and not owner_ok(b)]
    if in_host:
        flag(45,f"Uses the brand name '{in_host[0]}' on a domain it doesn't own ({reg})")
    # brand in the path counts only next to credential words (news articles mention brands all the time)
    asks_login=re.search(r"login|signin|sign-in|verify|password|account|webapps|kyc|otp|wallet",path)
    in_path=[b for b in BRANDS if len(b)>=4 and re.search(r"\b"+b+r"\b",path) and not owner_ok(b)] if asks_login else []
    if in_path and not in_host and not trusted:
        flag(25,f"Mentions '{in_path[0]}' in the link path on an unrelated site")

    # an official domain placed in front of the real one: paypal.com.verify-account.xyz
    fake_domain=next((d for d in OFFICIAL if sub and (sub==d or sub.endswith("."+d) or (d+".") in host) and not on_domain(host,d)),None)
    if fake_domain or re.search(r"\.(?:com|in|org|net)-[a-z]",host):
        flag(35,f"Hides a real-looking domain{(' ('+fake_domain+')') if fake_domain else ''} inside a different site's address")

    look=None if trusted else lookalike(host)
    if look:
        flag(50,f"Look-alike spelling of '{look}' (typosquatting)")

    # --- technical red flags ---
    if is_ip(host):
        flag(35,"Uses an IP address instead of a domain name")
    if "xn--" in host or any(ord(c)>127 for c in (p.netloc or "")):
        flag(35,"Uses an international (punycode) domain that can imitate real letters")
    if "@" in p.netloc:
        flag(35,"Contains @ in the address, which hides the real destination")
    if free_host:
        flag(25 if (in_host or in_path) else 15,f"Hosted on a free website platform ({free_host}) where anyone can publish")
    if tld in RISKY_TLDS and not trusted:
        flag(20,f"Uses a domain ending often abused for scams (.{tld})")
    if host in SHORTENERS:
        flag(25,"Uses a link shortener that hides the real destination")
    try:
        port=p.port
    except ValueError:
        port=-1 # malformed port such as ":abc"
    if port and port not in (80,443):
        flag(15,"Uses a non-standard port")
    if not trusted:
        words=[w for w in SUSPICIOUS_WORDS if w in lower]
        if words:
            flag(min(10+5*len(words),25),"Asks for sensitive actions: "+", ".join(words[:3]))
        if re.search(r"(?:^|[.-])(?:https?|www)(?:[.-]|$)",host.removeprefix("www.")) or "-www" in host:
            flag(20,"Puts 'http' or 'www' inside the domain name to look official")
        if label.count("-")>=2:
            flag(10,"Domain name joins several words with hyphens")
        if len(label)>=14 and entropy(label)>3.6:
            flag(15,"Domain name looks randomly generated")
        if sum(c.isdigit() for c in label)>=4:
            flag(10,"Domain name contains many digits")
        if len(host.split("."))>=5 and not is_ip(host):
            flag(15,"Contains many subdomain levels")
        if re.search(r"(?:gov|govt|government)",label) and not (host.endswith(".gov.in") or host.endswith(".gov") or host.endswith(".nic.in")):
            flag(30,"Claims to be government but isn't on a .gov / .gov.in / .nic.in domain")
    if DANGEROUS_FILES.search(path):
        flag(30,"Link downloads an app or program file")
    redirect=[v for vals in parse_qs(p.query).values() for v in vals if re.match(r"https?://",unquote(v))]
    if redirect and not trusted:
        flag(15,"Redirects to another website")
    if "//" in p.path:
        flag(10,"Contains a hidden redirect (// in the path)")
    if len(url)>180:
        flag(10,"Unusually long URL")
    if "%" in url and re.search(r"%[0-9a-f]{2}.*%[0-9a-f]{2}.*%[0-9a-f]{2}",lower):
        flag(5,"Contains a lot of encoded characters")

    return min(risk,100),reasons,good


def predict_url(url):
    url=str(url).strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*:",url.lower()):
        url="http://"+url

    features=extract_features(url)
    ml_phish=model.predict_proba([features])[0][1]  # class 1 = phishing
    risk,reasons,good=security_check(url)

    host=(urlparse(url).hostname or "").lower().removeprefix("www.")
    trusted=any(on_domain(host,d) for d in TRUSTED) and not any(on_domain(host,f) for f in FREE_HOSTS)

    # Rules carry the domain knowledge, so they lead; the URL-shape model is a second opinion.
    score=0.70*risk/100+0.30*ml_phish
    if trusted and risk<20:
        score=min(score,0.15)            # known official domain, nothing odd about it
    if risk>=45:
        score=max(score,0.80)            # impersonation, typosquat, IP, hidden domain...

    verdict="Phishing" if score>=0.45 else "Legitimate"
    confidence=score*100 if verdict=="Phishing" else (1-score)*100
    if verdict=="Legitimate" and not trusted:
        confidence=min(confidence,85)    # unknown sites: never claim certainty
        good.append("Not a known site - check the address carefully before entering details")

    return {
        "level":"High" if risk>=60 else "Medium" if risk>=30 else "Low",
        "verdict":verdict,
        "confidence":round(max(55,min(confidence,99)),2),
        "risk":risk,
        "reasons":reasons,
        "good":good,
        "domain":registered_domain(host),
        "ml_probability":round(ml_phish*100,2)
    }
