# BinSight RM0.20 Return Deposit Assessment

Research date: 29 August 2026. This document assesses a prototype policy. It does not claim that Malaysia has adopted a national RM0.20 beverage-container deposit.

For the citizen-facing sequence and its design rationale, see the [citizen return experience](CITIZEN_RETURN_EXPERIENCE.md).

## Decision

Keep **RM0.20 per eligible container** for the BinSight prototype and simulation. Describe it as a **refundable container deposit**, not a tax and not a general recycling reward.

Every participating shop charges the same RM0.20 deposit as a separate checkout line. The deposit follows the marked container. Whoever returns that eligible container receives RM0.20, whether they bought the drink, collected it for a community group, or picked it up as litter.

Use this wording in the citizen flow:

> RM0.20 refundable deposit per eligible container. Return any empty, accepted container carrying the regional deposit mark to recover the deposit.

Use `Deposit refund +RM0.20` on item events and receipts. Reserve `reward` for optional bonuses funded separately from the deposit pool.

## Why RM0.20 Is Defensible

### Local price signal

The official KPDN/DOSM [PriceCatcher August 2026 dataset](https://open.dosm.gov.my/data-catalogue/pricecatcher) contains daily prices and location lookups. Filtering `COCA COLA (TIN), 320 ml` for Selangor from 20 to 26 August produced 85 observations across 44 stores:

| Measure | Result |
| --- | ---: |
| Mean shelf price | RM1.93 |
| Median shelf price | RM1.90 |
| Observed range | RM1.00 to RM2.50 |
| RM0.20 as share of mean | 10.4% |
| RM0.20 as share of median | 10.5% |

A 20-sen deposit is noticeable against a typical single drink without dominating its price. Cheap water needs an affordability check: Jaya Grocer listed local 500-600 ml water from [RM0.80 to RM1.30](https://jgfreshub.jayagrocer.com/collections/water), making the temporary deposit 15% to 25% of the shelf price. A 24-container purchase also places RM4.80 on hold until return. Convenient redemption therefore matters as much as the nominal amount.

Malaysia already uses a 20-sen non-refundable plastic-bag pollution charge, as recorded in a [2024 parliamentary answer](https://www.nres.gov.my/parlimen/Lists/papar-Jawapan-Parlimen.aspx?ID=++++2595). That denomination is familiar, but BinSight must distinguish its fully refundable deposit from that charge.

### International evidence

The [OECD review of deposit-refund systems](https://one.oecd.org/document/ENV/WKP(2022)20/en/pdf) reports that higher purchasing-power-adjusted deposits correlate with higher return rates. It also reports 40% to 90% reductions in targeted-container litter across reviewed studies. The OECD warns that an excessive deposit can encourage product substitution and cross-border fraud, and that return-point convenience strongly affects participation.

Current schemes use different amounts:

| Jurisdiction | Deposit | Relevant evidence |
| --- | ---: | --- |
| Singapore | S$0.10 flat rate | The government selected 10 cents using public feedback and other jurisdictions, with staged targets of 60%, 70% and 80%. See the [MSE legislative statement](https://www.mse.gov.sg/latest-news/opening-speech-for-the-second-reading-of-the-rsa/) and [NEA consumer rules](https://www.nea.gov.sg/our-services/waste-management/beverage-container-return-scheme/for-consumers). |
| Australian states | A$0.10 flat rate | The [Australian government](https://www.dcceew.gov.au/environment/protection/waste/publications/national-waste-resource-recovery-reporting/product-stewardship-2024) records a 10-cent refund across state schemes. |
| Ireland | EUR0.15 or EUR0.25 by size | The [Irish government](https://www.gov.ie/en/department-of-climate-energy-and-the-environment/press-releases/irelands-deposit-return-scheme-is-live/) reports near-50% less bottle and can litter after the first year. |
| Germany | EUR0.25 for regulated one-way containers | The [German environment ministry](https://www.bundesumweltministerium.de/en/topics/circular-economy/types-of-waste-and-waste-flows/packaging-waste) specifies the uniform amount. |

Victoria modelled a 20-cent refund at roughly ten percentage points more return than 10 cents at maturity, although it retained 10 cents for national consistency. See the [2025 Victorian parliamentary response](https://www.parliament.vic.gov.au/492069/contentassets/be5d6aeef6d54f53805d3789bb5c5f4a/deeca-fpo-2024_25-qon.pdf). This supports the direction of the incentive, not a direct transfer of Australian values to Malaysia.

Taken together, RM0.20 sits in a credible middle position for a Malaysian pilot. RM0.10 risks becoming too small relative to the effort of storing and returning one container. RM0.30 would create a 30% temporary surcharge on a RM1.00 drink and needs stronger local evidence.

## Malaysian Policy Fit

Section 102 of Malaysia's [Solid Waste and Public Cleansing Management Act 2007, Act 672](https://eseranta.kpkt.gov.my/files/attach_y6scc0xy0tdfwfx.pdf) allows the Minister to establish a take-back and deposit-refund system and specify the products, deposit amount, labelling and distributor obligations. KPKT's [Circular Economy Blueprint for Solid Waste 2025-2035](https://www.kpkt.gov.my/index.php/pages/view/3392) and current government commentary support EPR and deposit-refund development.

The available official material does not establish a nationwide beverage-container amount or prove that a local operator can impose one as a tax. A real regional deployment needs KPKT, state/local-authority, consumer-pricing and Royal Malaysian Customs review. The prototype should state `simulated refundable deposit` until that authority exists.

## Required Scheme Rules

1. **Separate the drink price and deposit.** A receipt should show `Drink RM1.90 + refundable deposit RM0.20 = RM2.10`.
2. **Make the container the bearer instrument.** Do not bind redemption to the original purchaser, receipt or National ID. The app may authenticate a payout account, but ownership of the refund comes from presenting an eligible container.
3. **Verify deposit eligibility.** Computer vision can classify plastic, metal or glass, but it cannot prove that the regional deposit was paid. Add a registered deposit mark and barcode or signed serial. The machine must retain or irreversibly mark every refunded container.
4. **Use one regional clearing ledger.** Producers or importers fund deposits when containers enter the market. Retailers pass the deposit through. The operator pays refunds and reconciles sales, returns and handling fees.
5. **Ring-fence unclaimed deposits.** Use them for return points, collection, sorting, recycling, litter cleanup and public reporting. Do not treat them as retailer, app or municipal profit.
6. **Pay once per session.** Aggregate the 20-sen item credits and make one Bank Transfer or E-Wallet payment when the resident finishes. Per-item bank payments can cost more than the refund.
7. **Provide dense return access.** All shops selling marked drinks should charge the deposit. Large retailers should take returns; smaller shops need a nearby shared return point or a manual take-back route. The OECD finds that convenient return-to-retail networks often exceed depot-only participation.
8. **Handle glass separately.** The flat RM0.20 value is acceptable for the mock flow, but a physical pilot must test breakage, weight, storage and transport before including glass in the same machine.

The user's litter-collection idea matches established practice. NSW states that its operator pays the refund to any person who returns an eligible container, and it supports community collection and donations through [Return and Earn](https://www.epa.nsw.gov.au/Your-environment/Recycling-and-reuse/Return-and-earn). The OECD also documents deposit rings beside public bins so another person can collect and redeem containers without searching mixed waste.

## Financial Check

For every 100,000 eligible containers sold:

| Return rate | Deposits collected | Refunds paid | Unclaimed balance before costs |
| ---: | ---: | ---: | ---: |
| 60% | RM20,000 | RM12,000 | RM8,000 |
| 80% | RM20,000 | RM16,000 | RM4,000 |
| 90% | RM20,000 | RM18,000 | RM2,000 |

A successful scheme creates less unclaimed income. Producer fees, material revenue and transparent handling fees must therefore support operations; the design cannot depend on citizens failing to return containers.

## Validation Plan

Keep RM0.20 in the prototype and model RM0.10, RM0.20 and RM0.30 as sensitivity cases. For an eight-week regional pilot, report:

- eligible containers sold and returned;
- return rate by week and distance to return point;
- container-litter counts before and during the pilot;
- machine rejection, downtime and payout-failure rates;
- duplicate, counterfeit and out-of-region attempts;
- retailer handling time and storage cost;
- temporary household deposit exposure, including multipacks;
- use of every ringgit from unclaimed deposits.

Retain RM0.20 if convenient access produces a return rate near the 70% pilot target without material affordability or retailer-handling problems. Investigate RM0.30 only if return remains below 60% after access, machine reliability and public instructions have been corrected. Lowering the amount should require evidence that the temporary deposit deters purchases or places a disproportionate burden on low-cost water buyers.

## Confidence and Limits

**Recommendation confidence: medium-high for the prototype, medium for public deployment.** RM0.20 has a credible local price ratio and aligns with the direction of international evidence. Malaysia has not yet supplied local behavioural trial results, an official beverage-deposit amount, a retailer cost study or a mature return network. Those gaps prevent a claim that RM0.20 is proven optimal.
