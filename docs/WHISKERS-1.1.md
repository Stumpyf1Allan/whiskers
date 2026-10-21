# Whiskers 1.1: sections, the plan builder and parachutes

Whiskers 1.1 looks and works as 1.0 did: the same logo and the same seven screens
(Overview, Holdings, Allocation, Market watch, Markets, Activity, Settings). Everything
new is either switched off until somebody wants it, or sits one click in.

It is still a tool for keeping to your own plan. It is not financial advice.

## The optional sections: Mortgage and Retirement

Settings › **Sections** has a tick box for each. A section that is off shows nothing and
counts towards nothing, so a copy that never switches one on looks and adds up exactly as
1.0 did. When one is on:

- it adds one screen to the sidebar, after Activity;
- it adds one line to the Overview, under the figures, with a light;
- the Overview shows **net worth**, counting what the switched-on sections hold: your
  investments and cash always, the home and the mortgage with Mortgage, pension pots with
  Retirement. A pension that promises an income (final salary, an annuity) is shown as
  that income, never added in as though it could be spent tomorrow.

| Section | What it holds |
|---|---|
| **Mortgage** | The balance running down, interest against capital, the date the fixed rate ends (with a warning 200 days before), what an overpayment would save, what a new rate would cost, and your home with one value for it. |
| **Retirement** | One screen with three pages: **Year by year** (a plan one row a year to the end of retirement), **Pensions** (final salary, pots, annuities, South African retirement annuities) and the **State Pension**. Its own questions live here. |

A section switches on three ways: the tick box; an offer when a mortgage lender or a
pension provider is added from the list of firms; and the plan builder's last step, which
offers whichever suit the answers (someone near 70 with a mortgage: both; someone
decades from needing the money with no mortgage: neither). Switching one off deletes
nothing.

## The plan builder

Settings › Your plan › **Open the plan builder**. It is a page of its own, with its own
way back to Whiskers. It works offline and can see your holdings. Five short steps, saved
as each answer is given:

1. **You and this money**: when you'll start spending from it, how much you'd draw, any
   big cost within five years, how much of your essentials guaranteed income covers, an
   emergency fund, whether it should pay an income. With the Retirement section on, the
   questions about age and retirement come from there and aren't asked again.
2. **Risk**: what you would do if your investments fell by a third, what you actually did
   in 2020 or 2022, your experience, and what you'd rather have.
3. **How hands-on**: funds only, funds plus a few themes, or picking your own. It decides
   the size of the core and the room for themes and single companies.
4. **Your views**: a card for each theme (AI and big tech, healthcare, industrials,
   consumer brands, financials, property, oil and energy, gold, metals and miners,
   defence, UK companies, emerging markets, smaller companies, speculative growth,
   crypto), the ones in your money first, plus any of your own. On each: how strongly you
   believe in it (1 to 5), how worried you are it could fall hard (1 to 5), what you want
   to do (avoid it, hold a little, ride it, ride it with a parachute, or wait for a fall
   to buy), and, in your own words, why you hold it and what would change your mind. Then
   your worries about markets in general, anything you'd rather not own, and the one
   theme on your dial.
5. **What you hold**: the X-Ray (after Morningstar's): what your money is made of, where,
   the themes it rides on once funds are looked through, the biggest companies counting
   funds, and charges.

Then the answers are used in one of three ways. Nothing changes until you say so.

### A review of the plan you have

With a plan already in Whiskers, the builder **reviews** it against your answers instead
of replacing it. Your own targets stand unless an answer contradicts them: you said you'd
avoid a theme your plan holds; a theme you believe in strongly has no sleeve; a sleeve is
bigger than one theme gets for how hands-on you said you want to be; your plan holds more
in shares than your answers on risk allow. Each suggestion says why, and anything that
changes a target is left unticked for you to choose. Protections you asked for (the
parachute, a buying point) are ticked, ready to use. "Your targets after the ticked
changes" shows the result before anything is saved, and the targets always add up to
100: a change is balanced against your core.

### A fresh plan

For somebody with no plan yet, or who asks for one to compare: how much in shares comes
from three tests (Bogleheads, after Larry Swedroe): the risk you are *willing* to take,
*able* to take, and *need* to take (from the Retirement section, when it is on). The
plan takes the lower of willing and able, as the FCA expects advisers to; a real sale in a
past fall counts for more than a bold answer now; if the need is lower still, it says so.
Then:

- **the core** is a global index fund, at least 80% of the part in shares for funds only,
  50% with a few themes, 20% for someone who enjoys picking;
- **each theme** is sized by how strongly you believe in it, scaled by how hands-on you
  are (crypto and speculative growth stay small whatever the conviction);
- **your worries choose the defences**: a bubble or a crash, gold and cash; inflation,
  index-linked gilts; rising rates, short-dated gilts; a crash, cash for the ladder;
- **money already being spent, or needed within five years**, gets about two years of
  withdrawals in cash.

### A bespoke plan from Claude

For a plan written around you rather than built from rules: **Save the brief** writes a
markdown file with your answers, your views in your own words, what you hold (as shares of
the whole unless you ask for amounts), your current plan, the X-Ray, today's warning
lights and the exact plan-file format. Give it to Claude in a new chat. Paste Claude's
reply (or choose the file it sends) and **Check it**: Whiskers checks that it is a plan,
that the targets add up to 100, the bands and rules make sense and every step names real
sleeves, and how it sits against your answers (more risk than you said you'd take, a theme
you said you'd avoid, a parachute with no step). It shows what would change, sleeve by
sleeve, and loads it only when you say so.

**The written plan** is everything decided in one page, to print or save, including
**why you hold each theme** in your own words.

## Ride it, with a parachute

For a theme you believe in strongly but worry about (Allan's view of AI: "believe 5,
worried 4"), the parachute keeps a real stake and agrees the protections in advance:

- **a cap counting what funds hold**, five points above what the plan means to hold;
- **a trim on any one company** that grows past a limit, as the Alphabet rule does;
- **a step for when the theme's warning lights turn**: when half its lights are red (2 of
  the AI trade's 4), move a third of the sleeve into a defensive sleeve, decided now while
  things are calm;
- **a defensive sleeve to land in**: gold, or cash before gilts for somebody worried about
  rising rates.

When the lights turn, the step shows on the Overview and on Market watch, under **Your
agreed steps**, with your own reasons beside it. **I've done this** marks it taken (and,
if you like, moves the two targets so the next rebalance doesn't undo it); it applies
again the next time the lights turn. A **buying point** works the same way for a theme
you're waiting to buy: when it is far enough below its high, Whiskers says so. Whiskers
never trades.

## Getting files in

- **Import a file** (Settings › Importing files, or drop a file anywhere on the window):
  Freetrade's activity export, Trading 212's CSV, and the holdings files from Hargreaves
  Lansdown, AJ Bell, interactive investor and Vanguard Investor. The file is read and
  shown first; nothing goes in until *Import it*, and an overlapping file never counts
  anything twice.
- **The statements folder**: put each month's downloads in it and press Refresh. A file
  goes in by itself only when its layout is known *and* its filename names one platform;
  anything else waits, with the reason.
- **The monthly reminder**: a strip across the top on the day chosen, until that month's
  files are in, and a calendar file that repeats every month.
- **Find your platform or account** (Settings, Platforms): over 270 UK and South African
  banks, building societies, platforms and pension providers, each saying honestly how it
  keeps up to date: *connects automatically* (Trading 212, Monzo), *download a file*, or
  *type it in*.

A bank account can be in rand (or euros or dollars), converted at each day's rate
wherever pounds are added up, and checked against CoDI's R100,000 per bank.

## Trying 1.1 without touching your own Whiskers

Double-click **`Try Whiskers 1.1 (test copy).bat`**. It runs from the source folder and
keeps its data in `%LOCALAPPDATA%\Whiskers 1.1 test`, so your own Whiskers and the
family's copies are untouched. Delete that folder to start the test again. Settings ›
*Sample portfolio* loads made-up investments, with a home, a mortgage and two pensions for
the sections if you switch them on.

## For developers

- `engine/sections.py`: the switches, net worth and the Overview lines.
- `engine/builder.py`: the questions, risk, the review, the fresh plan, parachutes, the
  written plan, the brief and the check of a returned plan file.
- `engine/rules.py`: the parachute rule kinds `theme_step`, `theme_dip` and
  `any_company_cap`; `engine/plan.py` loads and saves them, with each sleeve's `theme`,
  `why` and `change`.
- The screens: `web/static/builder.js` (the plan builder), `mortgage.js`,
  `retirement.js`, `importer.js`; routes in `web/routes2.py`.
- `tests/test_sections.py` covers the new parts; `WHISKERS_FAKE_MARKET=1` invents prices
  for testing offline.
- The data folder, the keychain service name and the update address are unchanged, so a
  1.0 copy updates in place and keeps everything.

## 1.2: News on the Overview

- A News panel under *The big picture*: the day's five biggest business stories. Each
  headline opens the outlet's own page in your browser.
- Five outlets, read from their free public feeds: BBC News, The Guardian, Sky News, AP and
  CNBC (`market/news.py`). Stories under 24 hours old; videos, newsletters and opinion are
  dropped; the same story from several outlets counts once and ranks by how many carry it.
  No topic is favoured.
- Fetched in the background when the Overview opens and the list is over 15 minutes old,
  every 15 minutes while it stays open, and on Refresh (not within 2 minutes). One outlet down
  leaves the other four; all down leaves the last list. Kept in the `news` table on this device
  only; it does not travel to the phone's copy, but the `show_news` switch does.
- Settings, News: the switch, and whether each outlet is working.

