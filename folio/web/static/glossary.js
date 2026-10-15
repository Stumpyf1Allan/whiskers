/* Whiskers: the words it uses, in plain English.

   Opened from "Words" in the sidebar, Settings › Help and the plan review. Each meaning is
   written here in the app's own words; the link, where there is one, goes to a fuller
   explanation (Investopedia for general investing terms, GOV.UK and the official schemes
   for UK rules). Links open in the computer's own browser like every other link. */

const GLOSSARY = [
  { t: 'Annuity', d: 'An income for life (or for a set time) bought with money from a pension pot. Rates follow gilt yields, so a pound buys more income when interest rates are high.', u: 'https://www.investopedia.com/terms/a/annuity.asp' },
  { t: 'Asset allocation', a: 'mix', d: 'How your money is split between kinds of investment: shares, bonds, cash, gold, property. It decides most of the ups and downs you will feel.', u: 'https://www.investopedia.com/terms/a/assetallocation.asp' },
  { t: 'Band', a: 'sleeve band drift', d: 'How far a sleeve can drift from its target before Whiskers suggests putting it back. A 10% target with a ±2-point band is fine anywhere from 8% to 12%.' },
  { t: 'Bed and ISA', d: 'Selling an investment in a general account and buying it again inside an ISA, so its future growth and income are free of tax. The sale can make a taxable gain, so check the gain first.', u: 'https://www.gov.uk/individual-savings-accounts' },
  { t: 'Bonds and gilts', a: 'bond gilt treasury', d: 'A bond is a loan to a government or a company that pays interest and returns the money on a set date. Gilts are UK government bonds. Bond prices fall when interest rates rise, and rise when rates fall.', u: 'https://www.investopedia.com/terms/b/bond.asp' },
  { t: 'Breakeven inflation', d: 'The inflation rate bond investors are pricing in: the gap between the yield on an ordinary government bond and on an inflation-linked one of the same length.' },
  { t: 'CAPE', a: 'shiller pe cyclically adjusted', d: 'Price against ten years of earnings after inflation, Robert Shiller’s measure of how dear shares are. High readings have come before poor ten-year returns, but say nothing reliable about the next year.', u: 'https://www.multpl.com/shiller-pe' },
  { t: 'Capacity for loss', a: 'able to take risk', d: 'How much your plans could take if investments fell without your life having to change: the “able” half of risk. Advisers must weigh it alongside the risk you are willing to take.' },
  { t: 'CoDI', a: 'south africa deposit insurance', d: 'South Africa’s deposit insurance: up to R100,000 per person per bank, interest included. Unit trusts and shares are not covered.', u: 'https://resbank.co.za/en/home/what-we-do/Deposit-insurance/CODI-Frequently-Asked-Questions' },
  { t: 'Defined benefit pension', a: 'final salary career average db nhs pension', d: 'A pension that promises so much a year for life, worked out from your pay and your years in the scheme, like the NHS, teachers’ or civil service schemes. The scheme, not you, carries the investment risk.', u: 'https://www.investopedia.com/terms/d/definedbenefitpensionplan.asp' },
  { t: 'Defined contribution pension', a: 'pension pot dc workplace personal', d: 'A pension made of what you and your employer pay in, plus its growth. What it gives you depends on the size of the pot and how you take it.', u: 'https://www.investopedia.com/terms/d/definedcontributionplan.asp' },
  { t: 'Diversification', d: 'Spreading money across many investments so that no single failure does much damage. One global index fund owns thousands of companies.', u: 'https://www.investopedia.com/terms/d/diversification.asp' },
  { t: 'Drawdown (pensions)', a: 'flexi-access', d: 'Leaving a pension pot invested and taking money out as you need it, instead of buying an annuity. The money left can still rise and fall.' },
  { t: 'Fall from high', a: 'drawdown peak', d: 'How far something is below its highest point: a fund at £80 after a high of £100 is 20% below its high.', u: 'https://www.investopedia.com/terms/d/drawdown.asp' },
  { t: 'Emergency fund', d: 'Easy-access cash for surprises, usually three to six months of essential spending, so a bad month never forces you to sell investments at a low.', u: 'https://www.investopedia.com/terms/e/emergency_fund.asp' },
  { t: 'Equity risk premium', a: 'erp damodaran', d: 'The extra yearly return shares are priced to give over safe government bonds. Professor Aswath Damodaran estimates it each month; lower means shares are dearer against bonds.', u: 'https://www.investopedia.com/terms/e/equityriskpremium.asp' },
  { t: 'Forward P/E', a: 'price earnings', d: 'Share price against the next twelve months’ expected earnings: a common measure of how dear shares are.', u: 'https://www.investopedia.com/terms/f/forwardpe.asp' },
  { t: 'FSCS', a: 'compensation protection limit', d: 'The UK’s compensation scheme: up to £120,000 per person per banking licence for savings, and up to £85,000 per firm if an investment firm fails with money missing. It does not cover investments falling in value.', u: 'https://www.fscs.org.uk/' },
  { t: 'General investment account', a: 'gia', d: 'An ordinary investment account with no tax shelter. Dividends and gains above the yearly allowances can be taxed.' },
  { t: 'Home bias', a: 'uk companies', d: 'Owning more of your own country’s companies than their share of the world. The UK is about 3% of the world’s stock markets.' },
  { t: 'Index fund', a: 'tracker etf passive global core', d: 'A fund that simply owns everything in an index, such as the whole world’s stock markets, at low cost. An ETF is one that trades on a stock exchange like a share.', u: 'https://www.investopedia.com/terms/i/indexfund.asp' },
  { t: 'Inflation', a: 'cpi prices', d: 'Prices rising over time, so each pound buys less. Whiskers’ retirement plan is in today’s money to take it out of the picture.', u: 'https://www.investopedia.com/terms/i/inflation.asp' },
  { t: 'Inheritance tax', a: 'iht estate', d: 'Tax on what someone leaves when they die, above the allowances (£325,000, plus up to £175,000 more for a home left to children or grandchildren). Whatever passes to a husband, wife or civil partner is free of it. From April 2027, unused pension pots count too.', u: 'https://www.gov.uk/inheritance-tax' },
  { t: 'ISA', a: 'individual savings account stocks and shares cash', d: 'A wrapper that keeps savings or investments free of UK income tax and capital gains tax. Up to £20,000 a year can go in, across all your ISAs; unused allowance doesn’t carry over.', u: 'https://www.gov.uk/individual-savings-accounts' },
  { t: 'Lasting power of attorney', a: 'lpa', d: 'A legal document naming someone to make decisions for you if you can’t: one for money and property, one for health and care. It has to be made while you can still make it.', u: 'https://www.gov.uk/power-of-attorney' },
  { t: 'Loan to value', a: 'ltv mortgage', d: 'The mortgage as a share of the home’s value. A lower loan to value usually gets cheaper rates.', u: 'https://www.investopedia.com/terms/l/loantovalue.asp' },
  { t: 'Lump sum allowance', a: 'tax-free cash', d: 'The most that can come out of all your pensions tax-free: £268,275 for most people. Normally a quarter of each pot, up to that limit.' },
  { t: 'National Insurance record', a: 'qualifying years ni gaps voluntary class 3', d: 'Each year you paid or were credited National Insurance counts towards the State Pension: 35 years for the full amount, at least 10 for any. Gaps can sometimes be filled by paying voluntary contributions.', u: 'https://www.gov.uk/voluntary-national-insurance-contributions' },
  { t: 'Ongoing charges (OCF)', a: 'fees costs expense ratio', d: 'A fund’s yearly running cost, as a share of what you hold in it: 0.2% a year on £10,000 is £20. It comes out of the fund’s price, so you never see a bill.', u: 'https://www.investopedia.com/terms/e/expenseratio.asp' },
  { t: 'Real return', a: 'after inflation', d: 'Growth after inflation. 6% growth with 2.5% inflation is about 3.4% real.', u: 'https://www.investopedia.com/terms/r/realrateofreturn.asp' },
  { t: 'Rebalancing', d: 'Bringing the mix back to its targets, usually by putting new money into what has fallen behind, or trimming what has run ahead.', u: 'https://www.investopedia.com/terms/r/rebalancing.asp' },
  { t: 'Salary sacrifice', d: 'Giving up some pay in return for your employer paying it into your pension. It saves National Insurance as well as income tax.' },
  { t: 'Sequence risk', a: 'order of returns', d: 'The danger of a big fall just as withdrawals begin: selling low in the first years does lasting damage. It is why the plan tests a fall in the year you stop work.' },
  { t: 'SIPP', a: 'self-invested personal pension', d: 'A pension you run yourself on an investment platform. Whiskers tracks it on the Investments tab, not under Pensions, so it is never counted twice.' },
  { t: 'Sleeve', d: 'A slice of your plan for one kind of investment (a global core, gilts, gold), with a target share of your money and a band around it. Each holding belongs to one sleeve.' },
  { t: 'Standard variable rate', a: 'svr revert rate', d: 'The lender’s own rate that a mortgage moves to when a fixed deal ends. It is usually well above the rate on a new fixed deal.' },
  { t: 'State Pension age', a: 'spa', d: 'When the State Pension starts: 66, rising to 67 between 2026 and 2028 depending on your date of birth.', u: 'https://www.gov.uk/state-pension-age' },
  { t: 'Thesis', a: 'reason for owning', d: 'For a single company: why you own it, what would change your mind, and when to check again. It makes the next fall far easier to judge.' },
  { t: 'Today’s money', a: 'real terms', d: 'Future amounts shown as what they would buy now: £20,000 in 2045 means what £20,000 buys today.' },
  { t: 'Trend (200-day average)', a: 'moving average', d: 'A price against its average over roughly the last 200 trading days: the usual test of whether a long-term trend is up or down.', u: 'https://www.investopedia.com/terms/m/movingaverage.asp' },
  { t: 'UFPLS', a: 'uncrystallised funds pension lump sum', d: 'Taking a pension pot in chunks, each a quarter tax-free and three quarters taxed as income, instead of a quarter up front.' },
  { t: 'VIX', a: 'volatility fear gauge', d: 'How much the US stock market is expected to swing over the next month. It jumps in a panic.', u: 'https://www.investopedia.com/terms/v/vix.asp' },
  { t: 'Willing, able and need', a: 'risk tolerance', d: 'Three tests of how much risk to take: the risk you are willing to take, the risk you are able to take without your plans failing, and the risk you need to take to reach your goals. The plan takes the lower of willing and able.', u: 'https://www.bogleheads.org/wiki/Risk_tolerance' },
  { t: 'Yield curve', a: 'inverted', d: 'Interest rates on government bonds, from short loans to long ones. When short rates sit above long ones (an inverted curve), a recession has often followed, though not always.', u: 'https://www.investopedia.com/terms/y/yieldcurve.asp' },
];

function glossaryRows(q) {
  const s = (q || '').trim().toLowerCase();
  const hits = GLOSSARY.filter(g => !s || `${g.t} ${g.a || ''} ${g.d}`.toLowerCase().includes(s));
  return hits.length ? hits.map(g => `<div class="gloss"><b>${esc(g.t)}</b><div class="small">${esc(g.d)}</div>${g.u ? `<a class="tiny" href="${esc(g.u)}">More about it</a>` : ''}</div>`).join('')
    : '<p class="muted small">Nothing matches. Try a shorter word.</p>';
}

function openGlossary(q = '') {
  openModal({ title: 'Words explained', wide: true, body: `
    <input type="search" id="gloss-q" placeholder="Look up a word, such as ISA or annuity" value="${esc(q)}" aria-label="Look up a word" style="width:100%">
    <div id="gloss-list" class="gloss-list" style="margin-top:12px">${glossaryRows(q)}</div>`,
    foot: '<button class="btn" data-act="close">Close</button>' });
  const box = $('#gloss-q');
  if (box) {
    box.addEventListener('input', () => { $('#gloss-list').innerHTML = glossaryRows(box.value); });
    setTimeout(() => box.focus(), 0);
  }
}
ACTS['glossary'] = () => openGlossary();

document.addEventListener('DOMContentLoaded', () => {
  const b = document.getElementById('words-btn');
  if (b) b.addEventListener('click', () => openGlossary());
});
