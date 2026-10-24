# GeoNames mapping audit: X based-in and job locations

Follow-up research: [Chinese administrative geography sources](../research/2026-10-23-170517-chinese-administrative-geography-sources.md) records official names/codes, statistical-area distinctions, Amap limitations and coordinate systems for future matching under Option C.

## Scope and evidence

- Read-only production snapshot, 2026-10-23 Japan time. Source tables: `x_account_details`, `account_based_in_mappings`, `regions`, `job_listings`. No X API calls or production writes.
- Country ID crosswalk: [GeoNames countryInfo.txt](https://download.geonames.org/export/dump/countryInfo.txt), retrieved 2026-10-23; SHA-256 `c55f638cfaafb4fe45a9aa15120a0f1f78e8a34a8e1847d7b9320cf740fbc9ab`.
- GeoNames IDs below are candidates obtained by joining the existing reviewed provider mapping through ISO-2 code. This proves code coverage, not that the wording denotes the whole country, or a political position.
- Owner decisions on October 24 resolve bare `Korea` to South Korea (1835841) and bare `Congo` to Democratic Republic of the Congo (203312), preserving source wording. Explicit North Korea and Republic of the Congo remain distinct. The counts and existing-target column below remain the October 23 snapshot.
- Job categories are first-pass conversion decisions from the exact text and source key. Most city/district IDs have not yet been individually verified against GeoNames.

## Results

- X `account_based_in`: 194 distinct nonblank values across 59,066 account rows. 179 map to country/territory codes (52,488 rows), and every code has a GeoNames country ID. 13 map to region definitions (5,925 rows). Two remain unmapped: `Congo` (13) and `Korea` (640).
- `Bonaire` currently maps to BQ, but GeoNames BQ ID 7626844 denotes Bonaire, Sint Eustatius and Saba; this is broader than the raw wording. Hong Kong, Macao, Palestine and Taiwan have IDs but need explicit territory/display policy.
- Job listings: 816 rows, 259 with multiple locations, 149 empty arrays, 972 location elements. There are 971 string elements with 57 distinct values, plus one structured object (`{"city": null, "country": "India", "admin_area": null}` on listing 797).
- The 13 broad X regions require definition matching; the provider-specific `Eastern Europe (Non-EU)` has no approved exact GeoNames counterpart. GeoNames continent/region names must not be silently equated with UN M49 membership.

## X based-in: full distinct inventory

| Provider value | Accounts | Existing target | GeoNames ID candidate | Assessment |
|---|---:|---|---:|---|
| Afghanistan | 10 | ISO-2 AF | 1149361 | Country-code crosswalk candidate |
| Africa | 708 | Region africa | — | Review definition against GeoNames |
| Albania | 24 | ISO-2 AL | 783754 | Country-code crosswalk candidate |
| Algeria | 61 | ISO-2 DZ | 2589581 | Country-code crosswalk candidate |
| Andorra | 9 | ISO-2 AD | 3041565 | Country-code crosswalk candidate |
| Angola | 3 | ISO-2 AO | 3351879 | Country-code crosswalk candidate |
| Anguilla | 1 | ISO-2 AI | 3573511 | Country-code crosswalk candidate |
| Argentina | 589 | ISO-2 AR | 3865483 | Country-code crosswalk candidate |
| Armenia | 32 | ISO-2 AM | 174982 | Country-code crosswalk candidate |
| Aruba | 1 | ISO-2 AW | 3577279 | Country-code crosswalk candidate |
| Australasia | 58 | Region australia-and-new-zealand | — | Review definition against GeoNames |
| Australia | 715 | ISO-2 AU | 2077456 | Country-code crosswalk candidate |
| Austria | 168 | ISO-2 AT | 2782113 | Country-code crosswalk candidate |
| Azerbaijan | 51 | ISO-2 AZ | 587116 | Country-code crosswalk candidate |
| Bahamas | 2 | ISO-2 BS | 3572887 | Country-code crosswalk candidate |
| Bahrain | 5 | ISO-2 BH | 290291 | Country-code crosswalk candidate |
| Bangladesh | 325 | ISO-2 BD | 1210997 | Country-code crosswalk candidate |
| Barbados | 1 | ISO-2 BB | 3374084 | Country-code crosswalk candidate |
| Belarus | 35 | ISO-2 BY | 630336 | Country-code crosswalk candidate |
| Belgium | 182 | ISO-2 BE | 2802361 | Country-code crosswalk candidate |
| Belize | 1 | ISO-2 BZ | 3582678 | Country-code crosswalk candidate |
| Benin | 11 | ISO-2 BJ | 2395170 | Country-code crosswalk candidate |
| Bermuda | 1 | ISO-2 BM | 3573345 | Country-code crosswalk candidate |
| Bolivia | 20 | ISO-2 BO | 3923057 | Country-code crosswalk candidate |
| Bonaire | 1 | ISO-2 BQ | 7626844 | Scope review: Bonaire vs BQ |
| Bosnia and Herzegovina | 20 | ISO-2 BA | 3277605 | Country-code crosswalk candidate |
| Botswana | 1 | ISO-2 BW | 933860 | Country-code crosswalk candidate |
| Brazil | 1244 | ISO-2 BR | 3469034 | Country-code crosswalk candidate |
| Brunei Darussalam | 3 | ISO-2 BN | 1820814 | Country-code crosswalk candidate |
| Bulgaria | 93 | ISO-2 BG | 732800 | Country-code crosswalk candidate |
| Burkina Faso | 5 | ISO-2 BF | 2361809 | Country-code crosswalk candidate |
| Burundi | 1 | ISO-2 BI | 433561 | Country-code crosswalk candidate |
| Cambodia | 20 | ISO-2 KH | 1831722 | Country-code crosswalk candidate |
| Cameroon | 17 | ISO-2 CM | 2233387 | Country-code crosswalk candidate |
| Canada | 1382 | ISO-2 CA | 6251999 | Country-code crosswalk candidate |
| Cape Verde | 1 | ISO-2 CV | 3374766 | Country-code crosswalk candidate |
| Caribbean | 17 | Region caribbean | — | Review definition against GeoNames |
| Cayman Islands | 2 | ISO-2 KY | 3580718 | Country-code crosswalk candidate |
| Central Asia | 30 | Region central-asia | — | Review definition against GeoNames |
| Chile | 175 | ISO-2 CL | 3895114 | Country-code crosswalk candidate |
| China | 23 | ISO-2 CN | 1814991 | Country-code crosswalk candidate |
| Colombia | 275 | ISO-2 CO | 3686110 | Country-code crosswalk candidate |
| Comoros | 1 | ISO-2 KM | 921929 | Country-code crosswalk candidate |
| Congo | 13 | Unresolved | 203312 | Owner default: Democratic Republic of the Congo |
| Costa Rica | 36 | ISO-2 CR | 3624060 | Country-code crosswalk candidate |
| Côte d'Ivoire | 10 | ISO-2 CI | 2287781 | Country-code crosswalk candidate |
| Croatia | 62 | ISO-2 HR | 3202326 | Country-code crosswalk candidate |
| Cuba | 13 | ISO-2 CU | 3562981 | Country-code crosswalk candidate |
| Cyprus | 42 | ISO-2 CY | 146669 | Country-code crosswalk candidate |
| Czechia | 2 | ISO-2 CZ | 3077311 | Country-code crosswalk candidate |
| Czech Republic | 308 | ISO-2 CZ | 3077311 | Country-code crosswalk candidate |
| Denmark | 104 | ISO-2 DK | 2623032 | Country-code crosswalk candidate |
| Djibouti | 1 | ISO-2 DJ | 223816 | Country-code crosswalk candidate |
| Dominican Republic | 50 | ISO-2 DO | 3508796 | Country-code crosswalk candidate |
| East Asia | 559 | Region eastern-asia | — | Review definition against GeoNames |
| Eastern Europe (Non-EU) | 111 | Region eastern-europe-non-eu | — | Provider-only region; local ID |
| Ecuador | 61 | ISO-2 EC | 3658394 | Country-code crosswalk candidate |
| Egypt | 180 | ISO-2 EG | 357994 | Country-code crosswalk candidate |
| El Salvador | 27 | ISO-2 SV | 3585968 | Country-code crosswalk candidate |
| Estonia | 53 | ISO-2 EE | 453733 | Country-code crosswalk candidate |
| Ethiopia | 23 | ISO-2 ET | 337996 | Country-code crosswalk candidate |
| Europe | 1274 | Region europe | — | Review definition against GeoNames |
| Fiji | 3 | ISO-2 FJ | 2205218 | Country-code crosswalk candidate |
| Finland | 197 | ISO-2 FI | 660013 | Country-code crosswalk candidate |
| France | 1594 | ISO-2 FR | 3017382 | Country-code crosswalk candidate |
| French Guiana | 1 | ISO-2 GF | 3381670 | Country-code crosswalk candidate |
| French Polynesia | 5 | ISO-2 PF | 4030656 | Country-code crosswalk candidate |
| Gabon | 1 | ISO-2 GA | 2400553 | Country-code crosswalk candidate |
| Gambia | 1 | ISO-2 GM | 2413451 | Country-code crosswalk candidate |
| Georgia | 67 | ISO-2 GE | 614540 | Country-code crosswalk candidate |
| Germany | 1637 | ISO-2 DE | 2921044 | Country-code crosswalk candidate |
| Ghana | 55 | ISO-2 GH | 2300660 | Country-code crosswalk candidate |
| Gibraltar | 1 | ISO-2 GI | 2411586 | Country-code crosswalk candidate |
| Greece | 125 | ISO-2 GR | 390903 | Country-code crosswalk candidate |
| Guatemala | 30 | ISO-2 GT | 3595528 | Country-code crosswalk candidate |
| Guernsey | 1 | ISO-2 GG | 3042362 | Country-code crosswalk candidate |
| Guinea | 2 | ISO-2 GN | 2420477 | Country-code crosswalk candidate |
| Guyana | 1 | ISO-2 GY | 3378535 | Country-code crosswalk candidate |
| Haiti | 1 | ISO-2 HT | 3723988 | Country-code crosswalk candidate |
| Honduras | 18 | ISO-2 HN | 3608932 | Country-code crosswalk candidate |
| Hong Kong | 1179 | ISO-2 HK | 1819730 | Territory/display policy |
| Hungary | 77 | ISO-2 HU | 719819 | Country-code crosswalk candidate |
| Iceland | 8 | ISO-2 IS | 2629691 | Country-code crosswalk candidate |
| India | 4119 | ISO-2 IN | 1269750 | Country-code crosswalk candidate |
| Indonesia | 967 | ISO-2 ID | 1643084 | Country-code crosswalk candidate |
| Iran | 6 | ISO-2 IR | 130758 | Country-code crosswalk candidate |
| Iraq | 27 | ISO-2 IQ | 99237 | Country-code crosswalk candidate |
| Ireland | 116 | ISO-2 IE | 2963597 | Country-code crosswalk candidate |
| Isle of Man | 1 | ISO-2 IM | 3042225 | Country-code crosswalk candidate |
| Israel | 227 | ISO-2 IL | 294640 | Country-code crosswalk candidate |
| Italy | 516 | ISO-2 IT | 3175395 | Country-code crosswalk candidate |
| Jamaica | 7 | ISO-2 JM | 3489940 | Country-code crosswalk candidate |
| Japan | 5957 | ISO-2 JP | 1861060 | Country-code crosswalk candidate |
| Jersey | 2 | ISO-2 JE | 3042142 | Country-code crosswalk candidate |
| Jordan | 25 | ISO-2 JO | 248816 | Country-code crosswalk candidate |
| Kazakhstan | 43 | ISO-2 KZ | 1522867 | Country-code crosswalk candidate |
| Kenya | 201 | ISO-2 KE | 192950 | Country-code crosswalk candidate |
| Korea | 640 | Unresolved | 1835841 | Owner default: South Korea |
| Kuwait | 31 | ISO-2 KW | 285570 | Country-code crosswalk candidate |
| Kyrgyzstan | 7 | ISO-2 KG | 1527747 | Country-code crosswalk candidate |
| Lao People's Democratic Republic | 3 | ISO-2 LA | 1655842 | Country-code crosswalk candidate |
| Latvia | 64 | ISO-2 LV | 458258 | Country-code crosswalk candidate |
| Lebanon | 23 | ISO-2 LB | 272103 | Country-code crosswalk candidate |
| Libya | 4 | ISO-2 LY | 2215636 | Country-code crosswalk candidate |
| Liechtenstein | 2 | ISO-2 LI | 3042058 | Country-code crosswalk candidate |
| Lithuania | 67 | ISO-2 LT | 597427 | Country-code crosswalk candidate |
| Luxembourg | 28 | ISO-2 LU | 2960313 | Country-code crosswalk candidate |
| Macao | 10 | ISO-2 MO | 1821275 | Territory/display policy |
| Macedonia | 17 | ISO-2 MK | 718075 | Country-code crosswalk candidate |
| Madagascar | 7 | ISO-2 MG | 1062947 | Country-code crosswalk candidate |
| Malawi | 6 | ISO-2 MW | 927384 | Country-code crosswalk candidate |
| Malaysia | 233 | ISO-2 MY | 1733045 | Country-code crosswalk candidate |
| Maldives | 8 | ISO-2 MV | 1282028 | Country-code crosswalk candidate |
| Mali | 1 | ISO-2 ML | 2453866 | Country-code crosswalk candidate |
| Malta | 17 | ISO-2 MT | 2562770 | Country-code crosswalk candidate |
| Martinique | 3 | ISO-2 MQ | 3570311 | Country-code crosswalk candidate |
| Mauritania | 2 | ISO-2 MR | 2378080 | Country-code crosswalk candidate |
| Mauritius | 5 | ISO-2 MU | 934292 | Country-code crosswalk candidate |
| Mexico | 510 | ISO-2 MX | 3996063 | Country-code crosswalk candidate |
| Moldova | 16 | ISO-2 MD | 617790 | Country-code crosswalk candidate |
| Mongolia | 15 | ISO-2 MN | 2029969 | Country-code crosswalk candidate |
| Montenegro | 10 | ISO-2 ME | 3194884 | Country-code crosswalk candidate |
| Morocco | 90 | ISO-2 MA | 2542007 | Country-code crosswalk candidate |
| Mozambique | 3 | ISO-2 MZ | 1036973 | Country-code crosswalk candidate |
| Myanmar | 5 | ISO-2 MM | 1327865 | Country-code crosswalk candidate |
| Namibia | 5 | ISO-2 NA | 3355338 | Country-code crosswalk candidate |
| Nepal | 60 | ISO-2 NP | 1282988 | Country-code crosswalk candidate |
| Netherlands | 595 | ISO-2 NL | 2750405 | Country-code crosswalk candidate |
| New Caledonia | 3 | ISO-2 NC | 2139685 | Country-code crosswalk candidate |
| New Zealand | 121 | ISO-2 NZ | 2186224 | Country-code crosswalk candidate |
| Nicaragua | 4 | ISO-2 NI | 3617476 | Country-code crosswalk candidate |
| Niger | 1 | ISO-2 NE | 2440476 | Country-code crosswalk candidate |
| Nigeria | 1001 | ISO-2 NG | 2328926 | Country-code crosswalk candidate |
| North Africa | 84 | Region northern-africa | — | Review definition against GeoNames |
| North America | 884 | Region northern-america | — | Review definition against GeoNames |
| Norway | 131 | ISO-2 NO | 3144096 | Country-code crosswalk candidate |
| Oman | 12 | ISO-2 OM | 286963 | Country-code crosswalk candidate |
| Pakistan | 455 | ISO-2 PK | 1168579 | Country-code crosswalk candidate |
| Palestine | 9 | ISO-2 PS | 6254930 | Territory/display policy |
| Panama | 31 | ISO-2 PA | 3703430 | Country-code crosswalk candidate |
| Papua New Guinea | 2 | ISO-2 PG | 2088628 | Country-code crosswalk candidate |
| Paraguay | 31 | ISO-2 PY | 3437598 | Country-code crosswalk candidate |
| Peru | 88 | ISO-2 PE | 3932488 | Country-code crosswalk candidate |
| Philippines | 239 | ISO-2 PH | 1694008 | Country-code crosswalk candidate |
| Poland | 942 | ISO-2 PL | 798544 | Country-code crosswalk candidate |
| Portugal | 228 | ISO-2 PT | 2264397 | Country-code crosswalk candidate |
| Puerto Rico | 31 | ISO-2 PR | 4566966 | Country-code crosswalk candidate |
| Qatar | 21 | ISO-2 QA | 289688 | Country-code crosswalk candidate |
| Réunion | 10 | ISO-2 RE | 935317 | Country-code crosswalk candidate |
| Romania | 173 | ISO-2 RO | 798549 | Country-code crosswalk candidate |
| Russian Federation | 23 | ISO-2 RU | 2017370 | Country-code crosswalk candidate |
| Rwanda | 11 | ISO-2 RW | 49518 | Country-code crosswalk candidate |
| Saudi Arabia | 263 | ISO-2 SA | 102358 | Country-code crosswalk candidate |
| Senegal | 41 | ISO-2 SN | 2245662 | Country-code crosswalk candidate |
| Serbia | 94 | ISO-2 RS | 6290252 | Country-code crosswalk candidate |
| Seychelles | 1 | ISO-2 SC | 241170 | Country-code crosswalk candidate |
| Sierra Leone | 2 | ISO-2 SL | 2403846 | Country-code crosswalk candidate |
| Singapore | 1099 | ISO-2 SG | 1880251 | Country-code crosswalk candidate |
| Slovakia | 53 | ISO-2 SK | 3057568 | Country-code crosswalk candidate |
| Slovenia | 59 | ISO-2 SI | 3190538 | Country-code crosswalk candidate |
| Somalia | 5 | ISO-2 SO | 51537 | Country-code crosswalk candidate |
| South Africa | 216 | ISO-2 ZA | 953987 | Country-code crosswalk candidate |
| South America | 240 | Region south-america | — | Review definition against GeoNames |
| South Asia | 910 | Region southern-asia | — | Review definition against GeoNames |
| Southeast Asia | 709 | Region south-eastern-asia | — | Review definition against GeoNames |
| South Korea | 1 | ISO-2 KR | 1835841 | Country-code crosswalk candidate |
| Spain | 1458 | ISO-2 ES | 2510769 | Country-code crosswalk candidate |
| Sri Lanka | 46 | ISO-2 LK | 1227603 | Country-code crosswalk candidate |
| Sudan | 2 | ISO-2 SD | 366755 | Country-code crosswalk candidate |
| Suriname | 1 | ISO-2 SR | 3382998 | Country-code crosswalk candidate |
| Sweden | 255 | ISO-2 SE | 2661886 | Country-code crosswalk candidate |
| Switzerland | 320 | ISO-2 CH | 2658434 | Country-code crosswalk candidate |
| Syrian Arab Republic | 8 | ISO-2 SY | 163843 | Country-code crosswalk candidate |
| Taiwan | 459 | ISO-2 TW | 1668284 | Territory/display policy |
| Thailand | 393 | ISO-2 TH | 1605651 | Country-code crosswalk candidate |
| Togo | 2 | ISO-2 TG | 2363686 | Country-code crosswalk candidate |
| Trinidad and Tobago | 9 | ISO-2 TT | 3573591 | Country-code crosswalk candidate |
| Tunisia | 32 | ISO-2 TN | 2464461 | Country-code crosswalk candidate |
| Turkey | 1506 | ISO-2 TR | 298795 | Country-code crosswalk candidate |
| Türkiye | 9 | ISO-2 TR | 298795 | Country-code crosswalk candidate |
| Uganda | 32 | ISO-2 UG | 226074 | Country-code crosswalk candidate |
| Ukraine | 288 | ISO-2 UA | 690791 | Country-code crosswalk candidate |
| United Arab Emirates | 228 | ISO-2 AE | 290557 | Country-code crosswalk candidate |
| United Kingdom | 1557 | ISO-2 GB | 2635167 | Country-code crosswalk candidate |
| United States | 14175 | ISO-2 US | 6252001 | Country-code crosswalk candidate |
| Uruguay | 47 | ISO-2 UY | 3439705 | Country-code crosswalk candidate |
| US Virgin Islands | 1 | ISO-2 VI | 4796775 | Country-code crosswalk candidate |
| Uzbekistan | 18 | ISO-2 UZ | 1512440 | Country-code crosswalk candidate |
| Venezuela | 85 | ISO-2 VE | 3625428 | Country-code crosswalk candidate |
| Viet Nam | 557 | ISO-2 VN | 1562822 | Country-code crosswalk candidate |
| West Asia | 341 | Region western-asia | — | Review definition against GeoNames |
| Yemen | 16 | ISO-2 YE | 69543 | Country-code crosswalk candidate |
| Zambia | 11 | ISO-2 ZM | 895949 | Country-code crosswalk candidate |
| Zimbabwe | 24 | ISO-2 ZW | 878675 | Country-code crosswalk candidate |

## Job locations: full distinct string inventory

| Source value | Occurrences | Source keys | Conversion decision |
|---|---:|---|---|
| Amsterdam | 1 | x-post | City/alias candidate; verify ID and source context |
| Bengaluru | 1 | x-post | City/alias candidate; verify ID and source context |
| Berlin | 11 | x-post | City/alias candidate; verify ID and source context |
| Berlin, Germany | 1 | x-post | Qualified place candidate; verify feature and hierarchy |
| Brazil | 2 | x-post | Country/territory candidate; apply display policy |
| Europe | 3 | x-post | Broad-region definition review |
| Genoa, Italy | 1 | x-post | Qualified place candidate; verify feature and hierarchy |
| Global (Remote) | 1 | x-post | No automatic place FK; arrangement or relative wording |
| Gurgaon, Sector 67 | 1 | x-post | Subcity precision review; do not reduce silently to Gurgaon |
| India | 4 | x-post | Country/territory candidate; apply display policy |
| Japan | 1 | x-post | Country/territory candidate; apply display policy |
| Latin America | 12 | x-post | Broad-region definition review |
| London | 9 | x-post | City/alias candidate; verify ID and source context |
| Menlo Park | 1 | x-post | City/alias candidate; verify ID and source context |
| New York, NY | 1 | x-post | Qualified place candidate; verify feature and hierarchy |
| NYC | 1 | x-post | City/alias candidate; verify ID and source context |
| Overseas | 1 | x-post | No automatic place FK; arrangement or relative wording |
| Paris | 12 | x-post | City/alias candidate; verify ID and source context |
| Remote | 3 | x-post | No automatic place FK; arrangement or relative wording |
| San Jose | 1 | x-post | City/alias candidate; verify ID and source context |
| Seattle | 1 | x-post | City/alias candidate; verify ID and source context |
| Sunnyvale, California, USA | 1 | x-post | Qualified place candidate; verify feature and hierarchy |
| Surat | 1 | x-post | City/alias candidate; verify ID and source context |
| Tokyo | 1 | x-post | City/alias candidate; verify ID and source context |
| United States | 2 | x-post | Country/territory candidate; apply display policy |
| US | 1 | x-post | Country/territory candidate; apply display policy |
| Warsaw | 1 | x-post | City/alias candidate; verify ID and source context |
| Woodbury, MN | 1 | x-post | Qualified place candidate; verify feature and hierarchy |
| Zürich | 5 | x-post | City/alias candidate; verify ID and source context |
| 上城区 | 7 | zhipu | District candidate; verify parent city/province from source |
| 上海 | 128 | minimax; qwen | City/alias candidate; verify ID and source context |
| 东京 | 1 | minimax | City/alias candidate; verify ID and source context |
| 中国香港 | 1 | minimax | Country/territory candidate; apply display policy |
| 伦敦 | 1 | minimax | City/alias candidate; verify ID and source context |
| 内蒙古 察哈尔右翼前旗 | 2 | deepseek | Qualified place candidate; verify feature and hierarchy |
| 北京 | 237 | minimax; qwen; x-post | City/alias candidate; verify ID and source context |
| 北京市 海淀区 | 29 | deepseek | Qualified place candidate; verify feature and hierarchy |
| 南山区 | 3 | kimi | District candidate; verify parent city/province from source |
| 双流区 | 1 | zhipu | District candidate; verify parent city/province from source |
| 台湾 | 1 | x-post | Country/territory candidate; apply display policy |
| 哈尔滨 | 1 | qwen | City/alias candidate; verify ID and source context |
| 广州 | 87 | qwen | City/alias candidate; verify ID and source context |
| 成都 | 1 | qwen | City/alias candidate; verify ID and source context |
| 成都市 | 2 | kimi | City/alias candidate; verify ID and source context |
| 拱墅区 | 3 | deepseek | District candidate; verify parent city/province from source |
| 新加坡 | 1 | minimax | Country/territory candidate; apply display policy |
| 旧金山 | 2 | minimax | City/alias candidate; verify ID and source context |
| 杭州 | 170 | qwen; x-post | City/alias candidate; verify ID and source context |
| 柏林 | 1 | minimax | City/alias candidate; verify ID and source context |
| 沈阳 | 1 | qwen | City/alias candidate; verify ID and source context |
| 浙江 拱墅区 | 29 | deepseek | Qualified place candidate; verify feature and hierarchy |
| 浦东新区 | 5 | zhipu | District candidate; verify parent city/province from source |
| 海淀区 | 125 | deepseek; kimi; zhipu | District candidate; verify parent city/province from source |
| 深圳 | 23 | minimax; qwen | City/alias candidate; verify ID and source context |
| 深圳市 | 6 | zhipu | City/alias candidate; verify ID and source context |
| 翔安区 | 4 | zhipu | District candidate; verify parent city/province from source |
| 黄浦区 | 17 | kimi | District candidate; verify parent city/province from source |

## Verified examples and conversion requirements

- [Beijing 1816670](https://www.geonames.org/1816670/beijing.html) lists `北京`; [Hangzhou 1808926](https://www.geonames.org/1808926/hangzhou.html) lists `杭州`.
- [GeoNames BQ country 7626844](https://www.geonames.org/countries/) is wider than literal `Bonaire`.
- Romanization is unsafe for district matching: [Huangpu District 6571343](https://www.geonames.org/6571343/huangpu-district.html) is in Guangzhou and has Chinese name `黄埔区`; the job value `黄浦区` has a different character and likely refers to Shanghai. Match exact script and parent context.
- `Remote`, `Global (Remote)` and `Overseas` must not be converted into guessed coordinates. Preserve arrangement and scope separately. One structured job element must survive the `JobListingLocation` conversion with its ordinal and `India` country.
- [GeoNames extract format](https://download.geonames.org/export/dump/readme.txt); [UN M49 definitions](https://unstats.un.org/unsd/methodology/m49/).
