# Agronomy rules and parameter evidence

Decision support, not a replacement for local extension officers. No result is an irrigation dose, permission to sow, predicted injury or yield forecast.

## Geographic scope

The requested districts are Bengaluru Rural, Kolar, Tumakuru, Chikkaballapura and Ramanagara. UAS Bengaluru's [agroclimatic-zone table](https://www.uasbangalore.edu.in/en/agroclimatic-zones-uas-bangalore/) places most of this district set in the Eastern Dry Zone; Tumakuru spans zones. This implementation follows the named districts rather than relabelling them all Southern Dry Zone. District is caller-supplied and has not been checked against plot coordinates. No automatic district or crop stage is inferred from location.

## Enabled values

Catalogue version 1.1.0 contains 18 enabled parameters: 14 numeric values and four verbatim calendar references. Every entry below was opened and read from its cited source. Checked on 2026-10-30. The international coefficients and national thermal limit are not local calibrations. Reference-only values are usable only with explicit request context and the limitations below. Calendar references do not enable a sowing decision.

FAO source: Allen, Pereira, Raes and Smith, Crop Evapotranspiration: Guidelines for Computing Crop Water Requirements, FAO Irrigation and Drainage Paper 56; publisher: Food and Agriculture Organization of the United Nations. [Chapter 6, Tables 11 and 12](https://www.fao.org/4/x0490e/x0490e0b.htm). Table locators are used because the opened version is the official HTML edition. Group-row initial values are identified explicitly; blank crop cells are not interpreted as zero.

| Crop | Parameter | Number or window as written | Source and exact locator | Regional qualification |
| --- | --- | --- | --- | --- |
| ragi | sowing_window | July 2nd week to August 2nd week | [ICAR-CRIDA district contingency plan; Agricultural Research Station, Chintamani (UAS Bengaluru)](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR15-KOLAR%2031.03.2011.pdf) — Section 1.12, normal sowing-window table, Kharif-Rainfed row, Ragi column; printed page not reliably recoverable from text extraction | Kolar only; historical 2011 document |
| paddy | heat_above_c | 35°C | [ICAR - National Rice Research Institute](https://icar-nrri.in/wp-content/uploads/2023/05/BOOK-PHOTOSYNTHESIS-CLIMATE-CHANGE.pdf#page=68) — PDF page 68, printed page 68, section 3.2, High Temperature Stress on Rice Grain Quality | National/international rice discussion; not calibrated for the named Karnataka districts |
| paddy | kc_initial | 1.05 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, Rice, initial column | International subhumid reference; not calibrated for the named Karnataka districts |
| paddy | kc_mid | 1.20 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, Rice, mid column | International subhumid reference; not calibrated for the named Karnataka districts |
| paddy | sowing_window | June 3rd week – September 2nd week | [ICAR-CRIDA district contingency plan; Agricultural Research Station, Chintamani (UAS Bengaluru)](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR15-KOLAR%2031.03.2011.pdf) — Section 1.12, normal sowing-window table, Kharif-Rainfed row, Paddy column; printed page not reliably recoverable from text extraction | Kolar only; historical 2011 document |
| maize | kc_initial | 0.3 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, i. Cereals group initial column | International subhumid reference; not calibrated for the named Karnataka districts |
| maize | kc_mid | 1.20 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, Maize, Field (grain), mid column | International subhumid reference; not calibrated for the named Karnataka districts |
| maize | days_initial | 20 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 11, Maize (grain), October, India (dry, cool), days_initial | India (dry, cool), October; not district-calibrated |
| maize | days_development | 35 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 11, Maize (grain), October, India (dry, cool), days_development | India (dry, cool), October; not district-calibrated |
| maize | days_mid | 40 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 11, Maize (grain), October, India (dry, cool), days_mid | India (dry, cool), October; not district-calibrated |
| maize | days_late | 30 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 11, Maize (grain), October, India (dry, cool), days_late | India (dry, cool), October; not district-calibrated |
| maize | sowing_window | May 4th week – September 2nd week | [ICAR-CRIDA district contingency plan; Agricultural Research Station, Chintamani (UAS Bengaluru)](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR15-KOLAR%2031.03.2011.pdf) — Section 1.12, normal sowing-window table, Kharif-Rainfed row, Maize column; printed page not reliably recoverable from text extraction | Kolar only; historical 2011 document |
| tur | sowing_window | May 4th week – July 2nd week | [ICAR-CRIDA district contingency plan; Agricultural Research Station, Chintamani (UAS Bengaluru)](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR15-KOLAR%2031.03.2011.pdf) — Section 1.12, normal sowing-window table, Kharif-Rainfed row, Redgram column; printed page not reliably recoverable from text extraction | Kolar only; historical 2011 document |
| groundnut | kc_initial | 0.4 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, e. Legumes group initial column | International subhumid reference; not calibrated for the named Karnataka districts |
| groundnut | kc_mid | 1.15 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, Groundnut (Peanut), mid column | International subhumid reference; not calibrated for the named Karnataka districts |
| groundnut | kc_end | 0.60 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, Groundnut (Peanut), end column | International subhumid reference; not calibrated for the named Karnataka districts |
| tomato | kc_initial | 0.6 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, b. Solanaceae group initial column | International subhumid reference; not calibrated for the named Karnataka districts |
| tomato | kc_mid | 1.15 | [FAO-56](https://www.fao.org/4/x0490e/x0490e0b.htm) — Table 12, Tomato, mid column, footnote 2 | International subhumid reference; not calibrated for the named Karnataka districts |

The Kolar source is Agriculture Contingency Plan for District: Kolar, hosted by ICAR-CRIDA, with Agricultural Research Station, Chintamani as the concerned station. Section 1.12 explicitly identifies the crop columns and rainfed/irrigated rows. Calendar wording is preserved without converting a numbered week into an invented date. These four windows are exposed only for district Kolar and identified as historical Kharif-rainfed references; they are not transferred to adjacent districts. The table itself is the exact locator; its printed page could not be reliably recovered from the available text extraction.

The rice heat source is Climate Change: Impact on Photosynthesis and Productivity of Rice, ICAR-NRRI, PDF page 68, section 3.2. Its discussion concerns several hours during flowering and cultivar differences. Daily maximum exceedance triggers inspection only when growing status and flowering are supplied. It is not proof of exposure duration, injury or safe conditions below the cutoff.

## Water-balance calculation

FAO-56 Chapter 6 defines standard crop ET as ETc = Kc × ET0. For each UTC forecast day the engine calculates a reference gross-rainfall shortfall D = max(0, ETc - P), all water depths in mm over the same day. This comparison is a planning indicator, not a full root-zone water balance or irrigation requirement. Gross precipitation is not effective precipitation. Stored soil water, runoff, percolation, irrigation, crop stress, salinity and efficiency are absent. FAO's [Chapter 8, equations 80-82 and soil-water discussion](https://www.fao.org/4/x0490e/x0490e0e.htm) explains additional crop-stress and storage inputs. No fraction of rainfall is invented.

Table 12 coefficients describe non-stressed, well-managed crops under reference subhumid conditions. Initial Kc depends strongly on wetting frequency; mid/end Kc may need wind/humidity adjustment. The current client does not supply all required inputs for that correction. Results are therefore labelled unadjusted FAO reference estimates. The request must set allow_fao_reference=true and supply a district in scope; otherwise the crop-stage calculation returns insufficient_data. This explicit choice is necessary because reference coefficients are not locally calibrated.

Two ways to identify stage are supported:

- A caller-declared water_stage (initial or mid) with stage_valid_from and stage_valid_until. The coefficient is applied only within that interval. No continuation is assumed after its end. A groundnut end coefficient is allowed for a single endpoint date only: Kc_end is not a constant coefficient for the whole late stage.
- For maize only, an October planting_date can select the FAO Table 11 India dry/cool example. With planting day numbered 1, initial is days 1-20, development 21-55, mid-season 56-95, and late season 96-125. Kc interpolates linearly from initial to mid during development following the Chapter 6 crop-coefficient curve. These are projected stages, not observations. Maize late-stage calculation stays unavailable because no Kc_end endpoint is selected. Non-October planting, before-planting dates and dates beyond the example season return insufficient_data. Table 11 itself cautions that its durations are examples and should be replaced by local observations.

For tomato mid-season the caller must explicitly state tomato_tall_staked=false; taller staking requires a different coefficient under Table 12 footnote 2 and is not silently approximated. Paddy initial requires paddy_standing_water=true; the tabulated coefficient refers to the standing-water regime and reference climate, not dry direct seeding. Neither flag verifies field conditions independently. Unknown conditions leave the calculation unavailable.

A dated task prints the forecast rainfall, reference stage ETc, chosen Kc, ET0 and shortfall. Full-precision values and citations remain in water_balance, while prose formats numbers to two decimals for water and three for Kc. Context, source request URL, fetch time, stale status, exact input paths and rule version accompany the calculation. Stale evidence can be inspected but cannot trigger a water or heat task. Missing data never becomes zero. These reasons are deterministic renderings of structured evidence. Optional agent explanations pass the shared numeric guardrail and degrade visibly when unavailable; the agent never changes the rule actions.

## Remaining disabled values and research findings

| Values | Crops / scope | Why disabled |
| --- | --- | --- |
| Kc initial/mid/end and all stage lengths | Ragi, tur | FAO-56 has generic Millet and Pulses entries, not verified finger-millet/pigeon-pea rows. No unsupported species substitution. |
| Kc_end | Maize, paddy, tomato | Table 12 gives condition-dependent alternatives/ranges; harvest/management endpoint unresolved. No arbitrary midpoint or range endpoint selected. |
| Stage lengths | Paddy, groundnut, tomato | Table 11 offers several region/season examples. None establishes the target district's cultivar and season; use an explicitly supplied stage interval instead. |
| Numeric rainfall onset and subsequent dry-spell criterion | All six crops, all five districts | No opened official passage verified a complete quantitative criterion. Seasonal normal monsoon dates and drought definitions do not establish onset conditions. |
| GDD base temperature | All six crops | No readable accepted ICAR/university bulletin verified the intended base/model for this scope. Search snippets and theses outside the requested bulletin scope were not promoted to parameters. |
| Heat limit other than paddy flowering; crop cold/frost limit | All remaining crop/stage combinations | No usable opened regional bulletin established the intended damage/screening limit. Optimum growth ranges and experimental treatment temperatures are not damage cutoffs. |
| Waterlogging excess, sowing temperature bounds and operational calendar/onset suitability | All crops | Missing calibrated field inputs and complete local criteria. Shallow soil moisture and rainfall alone do not establish inundation. |
| Groundnut calendar | Tumakuru | Section 1.12 prints Iune 1st week to July end. Defective month text is left unresolved rather than silently repaired. |
| Regional calendars outside Kolar | Bengaluru Rural, Chikkaballapura, Ramanagara, Tumakuru | Official plans were read but no additional calendars were activated. Chikkaballapura has corresponding week-based rows but is not assumed equivalent; Ramanagara's rainfed ragi row prints a sixth week of August, which is ambiguous. Other rows need crop/regime-specific validation before use. |
| Tomato calendar | All districts | No verified crop-specific table row enabled; a generic Vegetables row is not enough. |

Official district documents opened and read:

- [Agriculture Contingency Plan for District: Bengaluru Rural](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR3-Bengaluru_Rural%2031.1.2011.pdf), ICAR-CRIDA district plan; section 1.12. These historical plans are not live weather.
- [Agriculture Contingency Plan for District: Chikkaballapura](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR11-CHICKBALLAPUR%2031.03.2011.pdf), ICAR-CRIDA district plan; PDF page 6, section 1.12. These historical plans are not live weather.
- [Agriculture Contingency Plan for District: Kolar](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR15-KOLAR%2031.03.2011.pdf), ICAR-CRIDA district plan; section 1.12. These historical plans are not live weather.
- [Agriculture Contingency Plan for District: Ramanagara](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR19-%20Ramanagara%2031.05.2011.pdf), ICAR-CRIDA district plan; PDF page 7, section 1.12. These historical plans are not live weather.
- [Agriculture Contingency Plan for District: Tumakuru](https://www.icar-crida.res.in/CP-2012/statewiseplans/Karnataka%20(Pdf)/GKVK,%20Bangalore/KAR%2020-%20Tumkur%2031.05.2011.pdf), ICAR-CRIDA district plan; PDF page 6, section 1.12. These historical plans are not live weather.

The UAS Bengaluru Technologies developed for inclusion in PoP 2000-2023 document could not be read through the browser because of its size limit; no values were enabled from it. Assam Agricultural University's tomato page timed out; snippets were not used. Previous TNAU references remain contextual only, with no new numbers imported.

## Other pure rules

The existing functions remain pure, with explicit units and typed available/insufficient_data/invalid_input results. GDD is max(0, mean daily temperature - supplied base) in degC_day; heat days count strict exceedances; frost is a strict below-threshold screen; reference ET0 deficit is max(0, sum ET0 - sum rainfall). The simplified waterlogging screen compares rain minus non-overlapping infiltration, surface drainage and surface storage against a supplied limit. Sowing suitability requires all local calendar/temperature/soil readiness inputs. Configured disabled inputs prevent those generic functions from producing operational advice. Null, empty, mismatched, negative-water and non-finite inputs are explicitly handled.

## Verification

Tests cover all enabled Kc values, stage interval boundaries, each maize stage-length transition, monotonic shortfall, absent coefficients/measurements, unsupported months, management conditions, district filtering and invalid context. Existing threshold, missing-input, outage and stale-evidence tests remain. HTTP tests use only the isolated recorded source response; application code never loads recordings. A live plan request and response are documented separately in API.md. These checks do not establish agronomic field accuracy.

## Ragi and tur coefficient evidence

A further crop-specific search opened the IMD MAUSAM article [Influence of actual evapotranspiration, growing degree days and bright sunshine hours on yield of finger millet](https://mausamjournal.imd.gov.in/index.php/MAUSAM/article/view/1105), C. S. Patil and B. Puttanna, volume 60(3), pages 343-348 (2009). Its abstract reports a peak Kc of 1.02 on day 66 in a Bangalore rainfed study. That is an isolated peak, not initial/mid/end coefficients or a complete curve suitable for the current stage algorithm. The full PDF link timed out. An ICAR-NRRI millet book was found but the browser could not read its full text because of its size. No value was enabled from either snippet or inaccessible text.

No opened accepted source supplied a complete crop-specific tur Kc/stage parameter set. Ragi and tur therefore retain disabled coefficients and durations. Plans now include water_balance_availability explicitly saying that no water-balance rule exists for the selected crop, rather than presenting reference ET0 deficit as crop water need. Their reference weather metrics remain available when the forecast has inputs.

## Visible optional evidence

The Plot/Plan product presents reference crop-water calculations only where the request provides the existing inputs. No new crop threshold is inferred by the UI. SoilGrids is optional and not consumed by the pure assessment; absence cannot become a soil-readiness flag. NASA POWER remains a retrospective observation cross-check, never a forecast input. The weather chart and all forward tasks continue to use the Open-Meteo evidence attached to Plan. Climate normals and cross-source error scoring remain unavailable.
