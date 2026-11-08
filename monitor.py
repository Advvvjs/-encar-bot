import json, os, time, urllib.request, urllib.parse

BASE = ("Mileage.range(..250000)._.Hidden.N._.(Or.Separation.F._.Separation.B.)"
        "_.SellType.일반._.Condition.Record._.Year.range(202001..202212)")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "application/json",
    "Referer": "https://www.encar.com/",
    "Origin": "https://www.encar.com",
}
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


def build_q(s):
    block = (f"(C.CarType.{s['type']}._.(C.Manufacturer.{s['maker']}._."
             f"(C.ModelGroup.{s['group']}._.(C.Model.{s['model']}._.{s['tail']}))))")
    return f"(And.{BASE}._.{block})"


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(s):
    params = urllib.parse.urlencode(
        {"count": "true", "q": build_q(s), "sr": "|ModifiedDate|0|100"},
        quote_via=urllib.parse.quote, safe="()._")
    data = get_json("https://api.encar.com/v1/search/car/list/general?" + params)
    return data.get("SearchResults", [])


def usd_rate():
    try:
        return float(get_json("https://open.er-api.com/v6/latest/USD")["rates"]["KRW"])
    except Exception:
        return 1470.0


def tg(method, **params):
    if not TOKEN:
        print("no token:", method, params.get("text") or params.get("caption"))
        return
    data = urllib.parse.urlencode(params).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as r:
        r.read()


def send_car(s, c, rate):
    won = int(float(c.get("Price", 0)) * 10000)
    usd = int(won / rate)
    y = str(int(float(c.get("Year", 0) or 0)))
    year = f"{y[:4]}.{y[4:6]}" if len(y) >= 6 else y
    km = int(c.get("Mileage", 0) or 0)
    link = f"https://fem.encar.com/cars/detail/{c['Id']}"
    text = (f"🚗 #{s['n']} {s['name']}\n"
            f"{c.get('Manufacturer','')} {c.get('Model','')} {c.get('Badge','')}\n"
            f"📅 {year}  🛣 {km:,} км\n"
            f"💰 ₩{won:,} ≈ ${usd:,}\n"
            f"📍 {c.get('OfficeCityState','')}\n"
            f"🔗 {link}").replace(",", " ")
    photo = c.get("Photo")
    try:
        if photo:
            tg("sendPhoto", chat_id=CHAT, photo="https://ci.encar.com" + photo + "001.jpg", caption=text)
        else:
            tg("sendMessage", chat_id=CHAT, text=text)
    except Exception:
        tg("sendMessage", chat_id=CHAT, text=text)


def main():
    searches = json.load(open("searches.json", encoding="utf-8"))
    try:
        state = json.load(open("seen.json", encoding="utf-8"))
    except Exception:
        state = {}
    meta = state.setdefault("_meta", {})
    rate = usd_rate()
    fails, baseline_total, sent = 0, 0, 0
    last_err = ""

    for s in searches:
        key = str(s["n"])
        try:
            items = fetch(s)
        except Exception as e:
            fails += 1
            last_err = repr(e)
            print("ERROR search", key, last_err)
            continue
        first = key not in state
        seen = state.setdefault(key, [])
        limit = s.get("max_krw") or (s["max_usd"] * rate if s.get("max_usd") else None)
        for c in items:
            cid = str(c.get("Id"))
            won = float(c.get("Price", 0) or 0) * 10000
            if limit and won > limit:
                continue
            if cid in seen:
                continue
            seen.append(cid)
            if first:
                baseline_total += 1
            else:
                try:
                    send_car(s, c, rate)
                    sent += 1
                except Exception as e:
                    print("send error", e)
        state[key] = seen[-600:]
        time.sleep(1)

    if fails == len(searches):
        if not meta.get("blocked_notified"):
            try:
                tg("sendMessage", chat_id=CHAT,
                   text="⚠️ Encar не отвечает ни на один запрос. Возможно, блокирует GitHub. Ошибка: " + last_err[:300])
            except Exception:
                pass
            meta["blocked_notified"] = True
    else:
        meta["blocked_notified"] = False
        if baseline_total:
            tg("sendMessage", chat_id=CHAT,
               text=f"✅ Бот работает. Запомнил {baseline_total} текущих объявлений, дальше буду присылать только новые.")
    json.dump(state, open("seen.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"done: sent={sent} baseline={baseline_total} fails={fails}")


if __name__ == "__main__":
    main()
