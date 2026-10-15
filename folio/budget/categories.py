"""Categories for the Budget tab, and the rules that fill them in.

Brought from Mittens & Pence, with its order of precedence:
  1. A category set by hand: never overwritten.
  2. A rule the person made ("everything from this shop is Groceries").
  3. The built-in UK and South African merchant patterns below.
  4. Nothing, which the Transactions screen asks about.

Teaching it is one click: categorising a transaction offers to remember the merchant,
which then fills in every matching row too.
"""

from __future__ import annotations

import functools
import re

from .. import db

# (parent, child, [patterns]): matched against the description, lower-cased. From
# Mittens & Pence's categorise.py, where the order of these lines was earned one
# mis-filed transaction at a time (a supermarket's petrol station before its groceries).
BUILTIN = [
    # ---------------------------------------------------------------- income
    ("Income", "Salary", [r"\bsalary\b", r"\bpayroll\b", r"\bwages\b", r"nhs\s*bsa",
                          r"\bsal\b", r"\bpay\s*ref", r"\bstipend\b", r"salaris"]),
    ("Income", "Interest received", [r"\binterest\b", r"gross int", r"credit interest",
                                     r"rente"]),
    ("Income", "Dividends received", [r"\bdividend\b", r"\bdiv\b\s*pmt"]),
    ("Income", "Refunds", [r"\brefund\b", r"\breversal\b", r"chargeback"]),
    ("Income", "Rental income", [r"\brent received\b", r"tenant"]),

    # ---------------------------------------------------------------- home
    ("Home", "Rent", [r"\brent\b(?!al car)", r"letting", r"landlord"]),
    ("Home", "Mortgage", [r"mortgage", r"\bhalifax mtg\b", r"\bbond repayment\b",
                          r"home loan"]),
    ("Home", "Council tax / rates", [r"council tax", r"\bcouncil\b", r"municipal",
                                     r"rates.*municipal", r"\bcity of \w+"]),
    ("Home", "Home insurance", [r"home ins", r"buildings ins", r"contents ins"]),
    ("Home", "Repairs & maintenance", [r"\bb&q\b", r"screwfix", r"toolstation", r"wickes",
                                       r"homebase", r"builders warehouse", r"leroy merlin",
                                       r"plumber", r"electrician"]),
    ("Home", "Furniture & homeware", [r"\bikea\b", r"dunelm", r"the range", r"wayfair",
                                      r"\bmr price home\b", r"coricraft"]),
    ("Home", "Levies (SA)", [r"\blevy\b", r"levies", r"body corporate", r"\bhoa\b"]),
    ("Home", "Security (SA)", [r"\badt\b", r"fidelity adt", r"beagle watch", r"cs?s security",
                               r"\barmed response\b"]),

    # ---------------------------------------------------------------- utilities
    # Energy first, so a dual-fuel supplier is claimed before the bare \bgas\b pattern
    # below can take "BRITISH GAS" for a gas bill. Built-in rules of equal priority are
    # tried in the order they appear here.
    ("Utilities", "Energy", [r"octopus energy", r"british gas", r"edf energy", r"e\.?on",
                             r"ovo energy", r"scottish power", r"sse\b", r"utilita",
                             r"\bbulb energy\b", r"shell energy", r"so energy",
                             r"utility warehouse", r"\bovo\b", r"\bedf\b"]),
    ("Utilities", "Electricity", [r"\beskom\b", r"prepaid electricity", r"\bcity power\b"]),
    ("Utilities", "Gas", [r"^(?!.*(petrol|fuel|station|garage|forecourt)).*\bgas\b", r"calor"]),
    ("Utilities", "Water", [r"thames water", r"severn trent", r"anglian water", r"yorkshire water",
                            r"united utilities", r"south west water", r"\brand water\b",
                            r"\bwater\b.*(bill|utility)"]),
    ("Utilities", "Broadband", [r"\bbt\b", r"virgin media", r"sky broadband", r"talktalk",
                                r"plusnet", r"hyperoptic", r"community fib", r"\bafrihost\b",
                                r"\bwebafrica\b", r"\brain\b", r"\bmweb\b", r"vumatel"]),
    ("Utilities", "Mobile phone", [r"\bee\b", r"\bo2\b", r"vodafone", r"three\b", r"giffgaff",
                                   r"tesco mobile", r"\bid mobile\b", r"lebara", r"lyca",
                                   r"\bmtn\b", r"\btelkom\b", r"cell ?c", r"\bvodacom\b"]),
    ("Utilities", "TV licence & streaming", [r"tv licen[cs]e", r"\bnetflix\b", r"disney ?\+",
                                             r"amazon prime video", r"\bnow tv\b", r"\bhayu\b",
                                             r"\bshowmax\b", r"\bdstv\b", r"multichoice",
                                             r"apple tv", r"\bmubi\b", r"paramount\+"]),

    # Before the grocers below, because a supermarket forecourt is a petrol station
    # that happens to share a name with a shop. "TESCO PETROL 4021" was filed as the
    # week's groceries, which quietly moved a tank of fuel into the food budget.
    ("Transport", "Fuel", [r"(tesco|sainsbury\w*|asda|morrisons|waitrose|costco|pick n pay|engen|sasol)\b.{0,20}\b(petrol|fuel|filling|forecourt|pfs)\b"]),

    # ---------------------------------------------------------------- food
    ("Food & Drink", "Groceries", [r"tesco", r"sainsbury", r"asda", r"morrisons", r"aldi",
                                   r"\blidl\b", r"waitrose", r"\bco-?op\b", r"iceland",
                                   r"marks ?&? ?spencer", r"\bm&s\b", r"ocado", r"budgens",
                                   r"\bwoolworths\b", r"\bcheckers\b", r"\bpick n pay\b",
                                   r"\bshoprite\b", r"\bspar\b", r"food ?lover", r"\bmakro\b"]),
    ("Food & Drink", "Restaurants & takeaway", [r"deliveroo", r"just ?eat", r"uber ?eats",
                                                r"\bnando", r"mcdonald", r"\bkfc\b", r"burger king",
                                                r"pizza", r"\bwagamama\b", r"greggs", r"subway",
                                                r"restaurant", r"\bmr d food\b", r"\bsteers\b",
                                                r"\bwimpy\b", r"\bocean basket\b", r"\bspur\b"]),
    ("Food & Drink", "Coffee & snacks", [r"costa", r"starbucks", r"pret", r"caffe nero",
                                         r"\bcafe\b", r"coffee", r"\bvida e\b", r"seattle coffee",
                                         r"bootlegger"]),
    ("Food & Drink", "Alcohol", [r"majestic wine", r"\bbwsw?\b", r"wine", r"brewdog",
                                 r"\bliquor\b", r"\btops\b", r"\bultra liquors\b"]),

    # ---------------------------------------------------------------- transport
    ("Transport", "Fuel", [r"\bshell\b", r"\bbp\b", r"\besso\b", r"texaco", r"\bgulf\b",
                           r"\bjet\b\s*fuel", r"\bengen\b", r"\bsasol\b", r"\bcaltex\b",
                           r"\btotal\b.*garage", r"petrol", r"fuel"]),
    ("Transport", "Public transport", [r"\btfl\b", r"transport for london", r"trainline",
                                       r"\bgwr\b", r"avanti", r"northern rail", r"national rail",
                                       r"\bmetrobus\b", r"gautrain", r"\bmyciti\b"]),
    ("Transport", "Taxi & rideshare", [r"\buber\b(?! ?eats)", r"\bbolt\b", r"\blyft\b",
                                       r"free ?now", r"\btaxi\b", r"\bola\b"]),
    ("Transport", "Car insurance", [r"car ins", r"motor ins", r"admiral", r"direct line",
                                    r"aviva.*motor", r"\bhollard\b", r"\boutsurance\b",
                                    r"\bmiway\b", r"\bnaked\b", r"king price"]),
    ("Transport", "Servicing & MOT", [r"\bmot\b", r"kwik ?fit", r"halfords", r"\bservice\b.*car",
                                      r"\bmidas\b", r"\btiger wheel\b", r"supa ?quick"]),
    ("Transport", "Parking & tolls", [r"parking", r"\bringgo\b", r"\bjustpark\b", r"dart charge",
                                      r"congestion", r"\bsanral\b", r"\betoll\b", r"\btoll\b"]),
    ("Transport", "Road tax / licence", [r"\bdvla\b", r"vehicle tax", r"road tax",
                                         r"licence renewal", r"natis"]),
    ("Transport", "Car finance", [r"car finance", r"\bpcp\b", r"vehicle finance", r"wesbank",
                                  r"\bmfc\b", r"vehicle asset"]),

    # ---------------------------------------------------------------- health
    ("Health", "Medical aid / health insurance", [r"\bbupa\b", r"\bvitality\b", r"\baxa health\b",
                                                  r"\bdiscovery health\b", r"\bmomentum health\b",
                                                  r"\bbonitas\b", r"\bmedihelp\b", r"medical aid",
                                                  r"\bdiscovery\b.*(health|medical)"]),
    ("Health", "Pharmacy", [r"\bboots\b", r"superdrug", r"pharmacy", r"\bclicks\b",
                            r"\bdis-?chem\b", r"lloyds pharmacy"]),
    ("Health", "Dentist & optician", [r"dentist", r"dental", r"specsavers", r"vision express",
                                      r"optician", r"\bmellins\b"]),
    ("Health", "Gym & fitness", [r"puregym", r"\bthe gym\b", r"david lloyd", r"nuffield health",
                                 r"\banytime fitness\b", r"\bvirgin active\b", r"\bplanet fitness\b",
                                 r"\bgym\b", r"\bpeloton\b", r"\bstrava\b"]),

    # ---------------------------------------------------------------- family
    ("Family", "Childcare", [r"nursery", r"childminder", r"childcare", r"after ?school",
                             r"\bcreche\b", r"\bcrèche\b"]),
    ("Family", "School fees", [r"school fee", r"\bschool\b", r"tuition", r"university",
                               r"\bpta\b"]),
    ("Family", "Pets", [r"pets ?at ?home", r"\bvet\b", r"veterinary", r"\bpetstop\b",
                        r"\bwestern shoppe\b", r"pet ?shop"]),

    # ---------------------------------------------------------------- shopping
    ("Shopping", "Clothing", [r"\bzara\b", r"\bh&m\b", r"\bnext\b(?=\s*(retail|plc|stores?|$))",
                              r"primark", r"uniqlo",
                              r"asos", r"\bjd sports\b", r"sports ?direct", r"\bmr price\b",
                              r"\btruworths\b", r"\bfoschini\b", r"\bcotton on\b", r"\bmarkham\b"]),
    ("Shopping", "Electronics", [r"currys", r"\bapple store\b", r"\bapple\.com\b",
                                 r"incredible connect", r"\bistore\b", r"\bgame\b\s*stores"]),
    # A shop that sells everything cannot be guessed at from the name of the shop.
    # Amazon used to land in Electronics for want of anywhere better, which made a
    # nappy order and a kettle both read as gadgets; the honest answer is "general
    # shopping", and split the ones that matter.
    ("Shopping", "Household & general", [r"\bamazon\b(?! ?prime)", r"\bamzn(?! ?prime)", r"\bebay\b",
                                         r"\btakealot\b", r"argos", r"john lewis",
                                         r"\bwilko\b", r"home bargains", r"\bb ?& ?m\b",
                                         r"poundland", r"\bpound ?stretcher\b",
                                         r"robert dyas", r"\bsavers\b", r"\btk ?maxx\b",
                                         r"\bhobbycraft\b", r"\bpep\b\s*stores"]),
    ("Shopping", "Books & media", [r"waterstones", r"\bkindle\b", r"audible", r"\bexclusive books\b",
                                   r"\bbargain books\b"]),
    # "gift" alone swallowed GIFT AID, which is a charitable donation and belongs
    # nowhere near a presents budget.
    ("Shopping", "Gifts given", [r"\bgift(?!\s*aid)\b", r"\bpresent\b", r"moonpig",
                                 r"netflorist"]),

    # ---------------------------------------------------------------- travel
    ("Travel", "Flights", [r"\bba\.com\b", r"british airways", r"easyjet", r"ryanair",
                           r"wizz ?air", r"\bjet2\b", r"emirates", r"\bklm\b", r"lufthansa",
                           r"\bflysafair\b", r"\bkulula\b", r"\bairlink\b", r"\bcemair\b",
                           r"\bairline\b", r"\bskyscanner\b"]),
    ("Travel", "Accommodation", [r"booking\.com", r"airbnb", r"\bhotel\b", r"premier inn",
                                 r"travelodge", r"\bexpedia\b", r"\bhotels\.com\b", r"\blekkeslaap\b"]),
    ("Travel", "Travel insurance", [r"travel ins"]),

    # ---------------------------------------------------------------- subscriptions
    ("Subscriptions", "Software", [r"\badobe\b", r"microsoft ?365", r"\bgoogle one\b",
                                   r"\bicloud\b", r"\bdropbox\b", r"\bnotion\b", r"\bcanva\b",
                                   r"\bopenai\b", r"\banthropic\b", r"\bgithub\b", r"\b1password\b",
                                   r"\bnordvpn\b", r"\bxero\b", r"\bquickbooks\b"]),
    ("Subscriptions", "Music & video", [r"amazon ?prime", r"\bprime video\b",
                                        r"spotify", r"apple ?music", r"\byoutube premium\b",
                                        r"\bdeezer\b", r"\btidal\b"]),
    ("Subscriptions", "News & magazines", [r"\bguardian\b", r"\btimes\b\s*sub", r"telegraph",
                                           r"\bnews24\b", r"\bdaily maverick\b", r"\bft\.com\b",
                                           r"\beconomist\b", r"\bnew york times\b"]),
    ("Subscriptions", "Memberships", [r"\bnational trust\b", r"\bgmc\b", r"\bbma\b", r"\brcp\b",
                                      r"\brcoa\b", r"\bhpcsa\b", r"\bsasa\b", r"\bmps\b",
                                      r"\bmdu\b", r"medical protection", r"membership",
                                      r"subscription"]),

    # ---------------------------------------------------------------- financial
    ("Financial", "Bank charges", [r"service charge", r"account fee", r"monthly fee",
                                   r"maintenance fee", r"bank charge", r"\boverdraft\b"]),
    ("Financial", "Interest & fees", [r"interest charged", r"late fee", r"\bapr\b"]),
    ("Financial", "Foreign exchange fees", [r"\bfx fee\b", r"non-?sterling", r"currency conversion",
                                            r"international fee"]),
    ("Financial", "Credit card payment", [r"credit card payment", r"card payment thank",
                                          r"\bcc payment\b"]),
    ("Financial", "Loan repayment", [r"loan repay", r"\bloan\b", r"personal loan"]),
    ("Financial", "Tax", [r"\bhmrc\b", r"\bsars\b", r"\bincome tax\b", r"self assessment",
                          r"\bpaye\b", r"\bvat\b"]),

    # ---------------------------------------------------------------- saving & investing
    ("Saving & Investing", "ISA contribution", [r"\bisa\b", r"stocks ?& ?shares"]),
    ("Saving & Investing", "SIPP / pension contribution", [r"\bsipp\b", r"pension contrib",
                                                           r"\bpensionbee\b", r"\bnest\b"]),
    ("Saving & Investing", "GIA contribution", [r"\bgia\b", r"general invest"]),
    ("Saving & Investing", "TFSA contribution (SA)", [r"\btfsa\b", r"tax-?free savings"]),
    ("Saving & Investing", "Retirement annuity (SA)", [r"retirement annuity", r"\bra contrib"]),
    ("Saving & Investing", "Other savings", [r"trading ?212", r"\bfreetrade\b", r"\bvanguard\b",
                                             r"hargreaves", r"\baj bell\b", r"interactive investor",
                                             r"\beasyequities\b", r"\ballan gray\b", r"\bsygnia\b",
                                             r"\b10x\b", r"\bcoronation\b", r"\bmoneybox\b",
                                             r"\bnutmeg\b", r"\binvestengine\b"]),

    # ---------------------------------------------------------------- giving
    ("Giving", "Charity", [r"\bgift ?aid\b", r"\bcharity\b", r"\bjustgiving\b", r"\bmacmillan\b", r"\boxfam\b",
                           r"\bunicef\b", r"\bdonation\b", r"\bgofundme\b"]),
    ("Giving", "Tithing", [r"\btithe\b", r"\bchurch\b", r"\bparish\b"]),

    # ---------------------------------------------------------------- transfers
    ("Transfers", "Cash withdrawal", [r"\batm\b", r"cash withdrawal", r"\bcashpoint\b",
                                      r"\blink\b\s*atm", r"cash @", r"\bsaswitch\b"]),
    ("Transfers", "Between own accounts", [r"transfer to", r"transfer from", r"\bsavings pot\b",
                                           r"\bpot transfer\b", r"own account"]),
    ("Transfers", "Cross-border transfer", [r"\bwise\b", r"transferwise", r"\bremitly\b",
                                            r"western union", r"\bxe\.com\b", r"currencyfair",
                                            r"\bmukuru\b", r"\bmama money\b"]),
]

#: What each top-level group counts as. "save" is money moved into savings or
#: investments: kept apart from spending, as Mittens & Pence does. "transfer" is money
#: moving between your own accounts, counted as neither.
KINDS = {"Income": "in", "Saving & Investing": "save", "Transfers": "transfer"}
KIND_OF_LINE = {("Financial", "Credit card payment"): "transfer"}


def kind_of(parent: str, name: str) -> str:
    return KIND_OF_LINE.get((parent, name)) or KINDS.get(parent, "out")


def seed() -> None:
    """The built-in categories, once. People can add their own beside them."""
    if db.scalar("SELECT COUNT(*) FROM txn_categories", (), 0):
        return
    with db.tx() as c:
        for i, (parent, name, _) in enumerate(BUILTIN):
            c.execute("INSERT OR IGNORE INTO txn_categories(parent,name,kind,sort) VALUES(?,?,?,?)",
                      (parent, name, kind_of(parent, name), i))


@functools.lru_cache(maxsize=1)
def _compiled() -> list[tuple[str, str, list[re.Pattern]]]:
    out = []
    for parent, name, pats in BUILTIN:
        out.append((parent, name, [re.compile(p, re.I) for p in pats]))
    return out


def all_categories() -> list[dict]:
    seed()
    return db.rows("SELECT * FROM txn_categories ORDER BY sort, parent, name")


def _ids() -> dict[tuple[str, str], int]:
    return {(r["parent"], r["name"]): r["id"] for r in all_categories()}


def guess(description: str, amount: float) -> tuple[int | None, str | None]:
    """(category id, how) for one transaction, or (None, None)."""
    text = (description or "").lower()
    for r in db.rows("SELECT pattern, category_id FROM txn_rules ORDER BY LENGTH(pattern) DESC, id"):
        if r["pattern"].lower() in text:
            return r["category_id"], "rule"
    ids = _ids()
    for parent, name, pats in _compiled():
        # Money in can only be income or a refund; a salary rule must not catch a payment out.
        if parent == "Income" and amount < 0:
            continue
        if any(p.search(text) for p in pats):
            cid = ids.get((parent, name))
            if cid:
                return cid, "builtin"
    return None, None


def apply(only_uncategorised: bool = True, platform_id: int | None = None) -> int:
    where = ["IFNULL(category_by,'') <> 'you'"]
    params: list = []
    if only_uncategorised:
        where.append("category_id IS NULL")
    if platform_id:
        where.append("platform_id=?")
        params.append(platform_id)
    rows = db.rows(f"SELECT id, description, amount FROM txns WHERE {' AND '.join(where)}", tuple(params))  # nosec B608  # fixed clauses
    n = 0
    with db.tx() as c:
        for t in rows:
            cid, how = guess(t["description"], t["amount"])
            if cid:
                c.execute("UPDATE txns SET category_id=?, category_by=? WHERE id=?", (cid, how, t["id"]))
                n += 1
    return n


def rule_key(text: str) -> str:
    """The merchant, without the noise banks add: card numbers, dates, reference codes."""
    t = re.sub(r"\b\d{2}[/-]\d{2}([/-]\d{2,4})?\b", " ", text or "")
    t = re.sub(r"\b\d{4,}\b", " ", t)
    t = re.sub(r"\b(card|ref|txn|pos|purchase|payment|dd|so|bp|ft|to|on|at)\b", " ", t, flags=re.I)
    t = re.sub(r"[^\w &'-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    words = t.split()
    return (" ".join(words[:3]) if words else (text or "")[:24]).lower()


def set_category(txn_id: int, category_id: int | None, remember: bool = False) -> dict:
    t = db.one("SELECT * FROM txns WHERE id=?", (txn_id,))
    if not t:
        raise ValueError("That transaction isn't there any more.")
    db.execute("UPDATE txns SET category_id=?, category_by=? WHERE id=?",
               (category_id, "you" if category_id else None, txn_id))
    filled = 0
    if remember and category_id:
        key = rule_key(t["description"])
        if len(key) >= 3:
            with db.tx() as c:
                c.execute("INSERT INTO txn_rules(pattern,category_id,created_at) VALUES(?,?,?) "
                          "ON CONFLICT(pattern) DO UPDATE SET category_id=excluded.category_id",
                          (key, category_id, db.now()))
            for r in db.rows("SELECT id, description FROM txns WHERE IFNULL(category_by,'') <> 'you' AND id<>?", (txn_id,)):
                if key in (r["description"] or "").lower():
                    db.execute("UPDATE txns SET category_id=?, category_by='rule' WHERE id=?", (category_id, r["id"]))
                    filled += 1
    return {"ok": True, "filled": filled}
