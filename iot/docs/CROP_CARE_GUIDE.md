# Crop Care Guide

How to grow, water, feed and protect the crops supported by the Smart Farm dashboard, written for conditions around **Alappuzha, Kerala**: hot and humid, two monsoons, acidic and often sandy or clayey soils.

> **Use this as a starting point, not a prescription.** Doses and timings vary with soil, variety and season. For official recommendations, check the **Kerala Agricultural University (KAU) Package of Practices** or ask your local **Krishi Bhavan**. Get a soil test before the first season: it tells you how much lime and fertilizer your field actually needs.

---

## Contents

1. [How the dashboard waters your crop](#1-how-the-dashboard-waters-your-crop)
2. [Working out how much water to give](#2-working-out-how-much-water-to-give)
3. [Kerala basics: seasons, soil and pests](#3-kerala-basics-seasons-soil-and-pests)
4. Crops with a dashboard preset: [Tomato](#tomato) · [Onion / Shallot](#onion--shallot) · [Paddy](#paddy--rice) · [Chilli](#chilli) · [Potato](#potato) · [Corn](#corn--maize) · [Cactus / Succulents](#cactus--succulents)
5. [Other common crops (use Custom cutoffs)](#5-other-common-crops-use-custom-cutoffs)
6. [Quick reference table](#6-quick-reference-table)

---

## 1. How the dashboard waters your crop

- **AUTO mode:** the pump starts when soil moisture drops **below the start cutoff** and stops when it **reaches the stop cutoff**. Choosing a crop in the **Crops** app sets both cutoffs. The **Today** app turns the forecast and this guide's water figures into a daily water amount and a fertilizer reminder; pump 2 (fertilizer) is run by hand from the **Fertilizer** app.
- **The soil % is a sensor reading, not a lab measurement.** The firmware maps the raw value (dry ≈ 1023, wet ≈ 300) to 0–100 %, and every sensor and soil type reads a little differently. Calibrate once per field:
  1. Note the dashboard reading when the soil is dry enough that the crop needs water. Squeeze a handful from root depth: it crumbles and won't hold shape.
  2. Water thoroughly, wait about 1 hour, and note the reading again. This is about "field capacity": the soil holds shape but no water drips out.
  3. Set **Start** a little above the dry reading and **Stop** a little below the wet reading. Those values become your **Custom** profile.
- **Place the sensor in the root zone:** 10–15 cm deep for vegetables and 5–8 cm for onion. Put it between two plants in the row, under a dripper's wetted area but not right below the emitter.
- **Rain:** the soil sensor already sees rain, so AUTO won't water wet soil. In heavy monsoon rain, switch to **MANUAL** and keep the pump off so the soil isn't waterlogged.
- **Rain tank:** when the dashboard says the rain tank is full, release the water and tap **Released · Reset**.

---

## 2. Working out how much water to give

A crop's daily water use is:

```
Crop water (mm/day) = ET0 × Kc
Litres per plant per day = ET0 × Kc × (row spacing m × plant spacing m) ÷ 0.9   (drip, 90 % efficient)
```

- **ET0** is the "reference" evaporation for your weather. Approximate values for Alappuzha:
  - **3–4 mm/day** during the monsoons (Jun–Nov)
  - **4–5 mm/day** in winter (Dec–Feb)
  - **5–6 mm/day** in the hot summer (Mar–May)
- **Kc** is the crop coefficient. It is low for young plants, highest at flowering and fruiting, and lower again near harvest. Each crop section below lists its Kc (FAO-56 values).
- **1 mm of water on 1 m² = 1 litre.**

**Example:** tomato at fruiting in April, with 60 × 45 cm spacing:
`5.5 × 1.15 × (0.60 × 0.45) ÷ 0.9 ≈ 1.9 L per plant per day`.

**Pump run time:** litres needed ÷ pump flow (L/min). Measure the flow once: time how long the pump takes to fill a 10 L bucket. For example, 50 plants × 1.9 L = 95 L, and at 8 L/min that's about 12 minutes a day. In AUTO mode the soil sensor decides the timing, and this figure tells you roughly how much tank water a day uses.

---

## 3. Kerala basics: seasons, soil and pests

| Season | Months | What it means for crops |
| :--- | :--- | :--- |
| South-west monsoon | June – September | Heavy rain. Grow on **raised beds or ridges** to avoid waterlogging; fungal diseases and bacterial wilt peak. |
| North-east monsoon | October – November | Moderate rain; good time to sow most winter vegetables at the end. |
| Winter / dry | December – February | **Best vegetable season.** Irrigation needed; fewer diseases. |
| Summer | March – May | Very hot; high water demand; mulch and shade young plants. |

**Soil:**
- **Acidity:** most Kerala soils are acidic (pH 4.5–5.5). Apply **lime or dolomite**, typically 250–500 kg/ha (25–50 g per m²), **2–3 weeks before** adding manure or fertilizer, and mix it into the soil. Never apply lime and fertilizer together.
- **Organic matter:** add well-rotted **farmyard manure (FYM) or compost**, about 20–25 t/ha (2–2.5 kg per m²) for vegetables, at land preparation.
- **Mulch:** dry leaves, straw or coir pith keep moisture even, cut weeds and save 20–30 % water.

**Common bio-controls used across Kerala:**

| Product | Use | Typical dose |
| :--- | :--- | :--- |
| *Pseudomonas fluorescens* | Wilt, leaf spots, seedling diseases; seed treatment, root dip and spray | 20 g per litre (2 %) |
| *Trichoderma* (enriched in compost or cow dung) | Soil-borne root rot and damping off | Mix 1 kg in 100 kg of moist manure, keep shaded 1–2 weeks, then apply |
| Neem oil emulsion (with soap) | Aphids, whitefly, mites, caterpillars (young) | 20 ml neem oil + 5 g soap per litre |
| Neem cake | Soil insects and nematodes; also a slow nutrient source | 250 kg/ha (25 g per m²) at planting |
| Yellow sticky traps | Whitefly, aphids, leaf miner | 10–12 per 1,000 m² at crop height |
| Bordeaux mixture 1 % | Fungal diseases (blight, leaf spot, rot) | Spray; prepare fresh, check with a knife (no copper coating = ready) |

Use chemical pesticides only when a pest is clearly beyond these controls. Follow the label and the **waiting period before harvest**, and wear gloves and a mask.

---

## 4. Crops with a dashboard preset

### Tomato
**Dashboard preset:** start below **35 %** · stop at **65 %**

| | |
| :--- | :--- |
| **Season** | Sow Sept–Oct for the winter crop (best); a summer crop is possible with shade. Avoid the June–Aug monsoon. |
| **Varieties for Kerala** | Bacterial-wilt resistant: **Anagha, Manulakshmi, Manuprabha, Vellayani Vijay, Akshaya** |
| **Spacing** | 60 cm × 45 cm, on ridges or raised beds |
| **Water need** | 400–600 mm per season · Kc 0.6 → 1.15 → 0.8 |

**Planting:** raise seedlings in a nursery or pro-trays. Transplant at 25–30 days (4–5 leaves), in the evening. Dip the roots in *Pseudomonas* 2 % for 20 minutes first.

**Watering:**
- Water lightly every day for the first week after transplanting.
- Then every 2–3 days in winter and daily in summer: about **1–1.5 L per plant per day** while growing and **1.5–2.5 L at flowering and fruiting**.
- **Most critical: flowering and fruit set.** Keep moisture **even**. Swings between dry and wet cause **fruit cracking** and **blossom-end rot** (a black patch at the fruit bottom).
- Water at the base, never over the leaves; wet leaves spread blight.

**Feeding:**
- At land prep: FYM plus lime as in section 3.
- **About 75 : 40 : 25 kg NPK per ha** (KAU). Apply half the N, all the P and half the K at planting; the rest in 2 splits at 30 and 45 days.
- Spray **calcium** (or apply lime) if blossom-end rot appears.

**Staking & pruning:** stake at 3–4 weeks. Remove the lower yellow leaves and the side shoots below the first flower cluster.

**Pests & diseases:**
| Problem | Signs | Treatment |
| :--- | :--- | :--- |
| **Bacterial wilt** (major in Kerala) | The whole plant wilts suddenly while still green; cut stem in water oozes white | No cure. Pull and destroy plants; use resistant varieties; lime the soil; drench *Pseudomonas* 2 %; rotate (no tomato, chilli or brinjal for 2–3 years) |
| Early / late blight | Brown target-like spots, then leaves dry | Remove lower leaves; spray Bordeaux 1 % or *Pseudomonas* 2 %; avoid overhead watering |
| Leaf curl virus | Small, curled, crinkled leaves; stunted plant | Spread by **whitefly**: yellow sticky traps, neem oil 2 %; uproot infected plants early |
| Fruit borer | Holes in fruit, caterpillars inside | Hand-pick; pheromone traps; neem oil early; *Bt* spray |

**Harvest:** 60–70 days after transplanting. Pick at the breaker stage (first pink colour) for transport, or red-ripe for home use, every 3–4 days.

---

### Onion / Shallot
**Dashboard preset:** start below **40 %** · stop at **70 %**

| | |
| :--- | :--- |
| **Season** | Oct–Nov sowing after the NE monsoon (rabi). Big onion grows best in the cooler highlands; **small onion / shallot** suits the plains. |
| **Spacing** | 15 cm × 10 cm on **raised beds** (good drainage is essential) |
| **Water need** | 350–550 mm per season · Kc 0.7 → 1.05 → 0.75 |

**Planting:**
- **Big onion:** transplant 6–7-week-old seedlings.
- **Shallot:** plant medium bulbs directly, with the top third cut off, about 2/3 deep.
- Dip roots or bulbs in *Pseudomonas* 2 % or *Trichoderma* before planting.

**Watering:**
- Onion roots are **shallow (15–20 cm)**, so give **light, frequent** watering. Keep the top soil moist but never waterlogged.
- In winter, water every 3–4 days; in warm weather, every 2 days.
- **Most critical: bulb formation**, about 45–90 days for big onion. Water stress then gives small bulbs.
- **Stop watering 10–15 days before harvest**, when the tops start falling over. This hardens the bulbs and helps them store.
- Wet soil at harvest causes rot and sprouting.

**Feeding:**
- FYM plus lime at bed preparation.
- Onion needs good **potash** and **sulphur** for bulb size and pungency.
- Apply N in 2–3 small splits up to about 60 days. Late nitrogen gives thick necks and poor storage.

**Pests & diseases:**
| Problem | Signs | Treatment |
| :--- | :--- | :--- |
| **Thrips** (main pest) | Silvery streaks, curling leaf tips | Blue sticky traps; neem oil 2 % sprays every 7–10 days; overhead sprinkling in dry spells helps |
| **Purple blotch** | Purple-brown oval spots with yellow edges | Avoid crowding and overhead watering; spray Bordeaux 1 % or *Pseudomonas* 2 % |
| Basal / bulb rot | Yellowing from the tip, rotten base | Better drainage; *Trichoderma* in soil; rotate crops; don't water late |

**Harvest:**
- Big onion: 110–130 days. Shallot: 60–75 days.
- Harvest when 50–75 % of the tops have fallen.
- Cure in shade for about 1 week (big onion) before storing in a dry, airy place.

---

### Paddy / Rice
**Dashboard preset:** start below **50 %** · stop at **85 %**

| | |
| :--- | :--- |
| **Season (Kuttanad / Alappuzha)** | **Puncha** (main, Nov–Mar) and **Virippu** (Apr/May–Aug) |
| **Varieties** | Uma (Mo-16), Jyothi, Kanchana, Shreyas; the saline-tolerant Vytilla varieties for salt-affected fields |
| **Spacing** | Transplant 20 × 15 cm (2–3 seedlings per hill), or direct seeding |
| **Water need** | 1,000–1,500 mm+ per season · Kc 1.05 → 1.2 → 0.9 |

**Watering:**
- Rice is the one crop here that likes **standing water**: keep **2–5 cm** in the field from transplanting to grain filling.
- **Alternate wetting and drying (AWD)** saves 20–30 % water with no yield loss. Let the water drop until the soil just cracks or is about 15 cm below the surface in a perforated tube, then flood again.
- **Never let the field dry at panicle initiation and flowering**, about 45–80 days. That causes empty grains.
- **Drain the field 10–15 days before harvest.**
- A soil moisture sensor is most useful for **upland, pot or tray paddy**. In flooded Kuttanad fields, check the water depth by eye.
- **Salinity:** in the dry season in Kuttanad, don't irrigate with salty backwater (check the water's salinity, EC).

**Feeding:**
- About **90 : 45 : 45 kg NPK per ha** for medium-duration varieties, 70 : 35 : 35 for short-duration (KAU).
- Apply lime at land prep in acidic or acid-sulphate soils.
- Split the N into 3 doses: basal, tillering and panicle initiation.
- Too much N invites pests and lodging.

**Pests & diseases:**
| Problem | Signs | Treatment |
| :--- | :--- | :--- |
| Stem borer | Dead hearts, white empty heads | *Trichogramma* egg cards; light traps; remove stubble after harvest |
| Leaf folder | Folded leaves, white streaks | *Trichogramma* cards; avoid excess N |
| Brown plant hopper | Circular patches drying ("hopper burn") | Drain the field for a few days; avoid excess N; alley-ways every 2 m |
| Blast | Spindle-shaped grey spots; neck rot | *Pseudomonas* 2 % seed treatment + spray; balanced N |
| Sheath blight | Oval greenish-grey lesions on sheaths | *Pseudomonas* spray; wider spacing |

**Harvest:** when 80–85 % of the grains are straw-coloured, about 30 days after flowering.

---

### Chilli
**Dashboard preset:** start below **25 %** · stop at **55 %**

| | |
| :--- | :--- |
| **Season** | Transplant May–June (rain-fed with drainage) or Sept–Oct (irrigated, best) |
| **Varieties** | **Ujwala** (bacterial-wilt resistant), Anugraha, Vellayani Athulya; *kanthari* (bird's-eye chilli) in homesteads |
| **Spacing** | 45 cm × 45 cm, on ridges or raised beds |
| **Water need** | 600–900 mm per season · Kc 0.6 → 1.05 → 0.9 |

**Watering:**
- Chilli hates **waterlogging**: wet feet cause root rot and flower drop. Let the top 2–3 cm dry between waterings.
- About **1–2 L per plant per day** at flowering in dry weather.
- **Most critical: flowering and fruit set.** Stress then causes flower and fruit drop.

**Feeding:** FYM plus lime; about **75 : 40 : 25 kg NPK per ha** (KAU). Give the N in splits at planting, 30 days and 60 days.

**Pests & diseases:**
| Problem | Signs | Treatment |
| :--- | :--- | :--- |
| **Leaf curl** (thrips, mites, virus) | Leaves curl up or down, crinkle; plant stunted | Neem oil 2 %; yellow and blue sticky traps; remove virus-infected plants; border crop of maize |
| Bacterial wilt | Sudden wilting | As for tomato; resistant Ujwala |
| Anthracnose / fruit rot | Sunken dark spots on ripe fruit | Remove infected fruit; Bordeaux 1 % or *Pseudomonas* 2 % |
| Damping off (nursery) | Seedlings collapse at soil line | *Trichoderma* in nursery mix; don't overwater |

**Harvest:** green chillies from about 75 days; pick every 7–10 days.

---

### Potato
**Dashboard preset:** start below **30 %** · stop at **60 %**

| | |
| :--- | :--- |
| **Season** | Cool weather needed: grows best in the Kerala **highlands** (e.g. Kanthalloor, Vattavada) or in the cool months. In hot lowlands, yields are low. |
| **Spacing** | 60 cm between ridges × 20 cm between seed tubers |
| **Water need** | 500–700 mm per season · Kc 0.5 → 1.15 → 0.75 |

**Planting:** use certified, sprouted seed tubers of 30–40 g, planted 5–7 cm deep on ridges. **Earth up** at 25–30 days to cover the forming tubers.

**Watering:**
- Give **frequent, light** watering. Potato roots are shallow and the tubers need even moisture.
- **Most critical: tuber initiation and bulking** (about 30–75 days). Uneven watering gives cracked or knobby tubers.
- **Stop watering 10 days before harvest.**

**Feeding:** potato is a heavy feeder, especially of **potash**. Apply FYM, then N in 2 splits (at planting and at earthing-up).

**Pests & diseases:**
| Problem | Signs | Treatment |
| :--- | :--- | :--- |
| **Late blight** | Water-soaked dark patches, white fungus under leaves in humid weather | Spray Bordeaux 1 % preventively in cloudy or humid spells; destroy infected haulms |
| Bacterial wilt | Wilting; ooze from cut tubers | Healthy seed; rotation; lime the soil |
| Tuber moth | Tunnels in tubers | Keep tubers covered with soil; harvest on time |

**Harvest:** 90–110 days, when the haulms (tops) turn yellow and dry. Cure in shade before storage.

---

### Corn / Maize
**Dashboard preset:** start below **30 %** · stop at **65 %**

| | |
| :--- | :--- |
| **Season** | Sept–Oct and Jan–Feb sowings; sweet corn and baby corn are popular near towns |
| **Spacing** | 60 cm × 25 cm (sweet corn), 60 cm × 20 cm (baby corn) |
| **Water need** | 500–800 mm per season · Kc 0.3 → 1.2 → 0.6 |

**Watering:**
- Moderate needs early on; peak demand comes at **tasseling and silking** (about 45–65 days). **Even 2–3 dry days then can cut yield by half.**
- Water at the base or in the furrows. Maize tolerates short dry spells while growing but not at silking.

**Feeding:** maize is a heavy **nitrogen** user. Apply FYM, then N in 3 splits (at sowing, knee-high around 30 days, and tasseling).

**Pests & diseases:**
| Problem | Signs | Treatment |
| :--- | :--- | :--- |
| **Fall armyworm** (major) | Ragged holes in the whorl; sawdust-like droppings | Check the whorls twice a week; hand-pick egg masses and larvae; put a pinch of **sand + lime (9:1)** into the whorls; neem oil early; *Bt* spray |
| Stem borer | Shot holes, dead heart | *Trichogramma* cards; destroy stubble |
| Leaf blight | Long grey-brown lesions | Resistant varieties; *Pseudomonas* spray |

**Harvest:**
- **Sweet corn:** 70–80 days, about 20 days after silking, when the silk browns and the kernels give milky juice.
- **Baby corn:** 1–3 days after the silk appears.
- **Grain maize:** when the husk is dry.

---

### Cactus / Succulents
**Dashboard preset:** start below **15 %** · stop at **35 %**

| | |
| :--- | :--- |
| **Where** | Pots, rooftops, rock gardens; also aloe vera and other drought-hardy plants |
| **Water need** | Very low: let the mix dry out **completely** between waterings |

**Care:**
- Use a **very free-draining mix**: about 1 part garden soil, 1 part coarse sand, 1 part brick pieces or perlite. Pots must have drainage holes.
- **Watering:**
  - In summer, water every 7–14 days, soaking the pot and letting it drain fully.
  - **During the monsoon, move pots under cover and stop watering.** Constant humidity is the main killer.
  - In winter, water every 2–4 weeks.
- **Root rot** (a soft, black base) comes from overwatering. Cut away the rotten tissue, dry the cutting for a week, and replant in dry mix.
- **Mealybugs** (white cottony tufts): wipe them off with a cotton bud dipped in alcohol, or spray neem oil.
- Give bright light, but shade from harsh afternoon sun if the plants turn yellow or brown.

---

## 5. Other common crops (use Custom cutoffs)

These aren't presets yet. Pick **Custom** and set the cutoffs shown. Then fine-tune them using the calibration steps in section 1.

| Crop | Season & spacing | Custom cutoffs | Watering | Key problems & treatment |
| :--- | :--- | :--- | :--- | :--- |
| **Okra / Bhindi** (Vendakka) | Feb–Mar, Jun–Jul, Sep–Oct · 60 × 45 cm | 35 % – 65 % | Every 2–3 days; critical at flowering & pod set | Yellow vein mosaic (whitefly): resistant **Arka Anamika, Salkeerthi**, sticky traps, neem oil · fruit & shoot borer: remove affected shoots and fruits |
| **Brinjal** (Vazhuthana) | Sept–Oct, May–Jun · 75 × 60 cm | 35 % – 65 % | Every 3–4 days; even moisture at fruiting | Bacterial wilt: resistant **Surya, Swetha, Haritha** · shoot & fruit borer: cut wilted shoots, pheromone traps |
| **Amaranthus** (Cheera) | Year-round · 30 × 20 cm | 40 % – 70 % | Light daily watering; shallow roots | Leaf spot (wet season): avoid overhead watering, *Pseudomonas* 2 % · leaf webber: neem oil |
| **Cowpea / Yard-long bean** (Payar) | Year-round · 2 m × 2 m pits on pandal | 35 % – 65 % | Every 2–3 days; critical at flowering | Aphids: neem oil, ladybird beetles · pod borer: hand-pick, neem oil |
| **Bitter gourd** (Pavakka) | Jan–Mar, Sep–Dec · 2 × 2 m pits on pandal | 40 % – 70 % | Every 2 days at fruiting; ~3–4 L per pit | **Fruit fly**: cover fruits, cue-lure traps, destroy fallen fruit · downy mildew: Bordeaux 1 % |
| **Banana (Nendran)** | Aug–Sep planting · 2 × 2 m | 40 % – 75 % | 10–15 L per plant per day in summer; never let it dry during bunch development | Pseudostem weevil: remove dried leaves, keep base clean · sigatoka leaf spot: remove infected leaves, Bordeaux 1 % |

---

## 6. Quick reference table

| Crop | Start / stop cutoff | Season water | Most critical watering stage | Stop watering |
| :--- | :--- | :--- | :--- | :--- |
| Tomato | 35 % / 65 % | 400–600 mm | Flowering & fruit set (keep even) | — (pick through season) |
| Onion / Shallot | 40 % / 70 % | 350–550 mm | Bulb formation | 10–15 days before harvest |
| Paddy | 50 % / 85 % | 1,000–1,500 mm+ | Panicle initiation & flowering | Drain 10–15 days before harvest |
| Chilli | 25 % / 55 % | 600–900 mm | Flowering & fruit set (no waterlogging) | — |
| Potato | 30 % / 60 % | 500–700 mm | Tuber initiation & bulking | 10 days before harvest |
| Corn | 30 % / 65 % | 500–800 mm | Tasseling & silking | When husks dry (grain) |
| Cactus | 15 % / 35 % | very low | — (let dry fully) | Monsoon: stop |

*Sources: FAO Irrigation & Drainage Paper 56 (crop coefficients, seasonal water needs); KAU Package of Practices Recommendations: Crops (varieties, fertilizer doses, bio-control). Confirm doses for your soil with the local Krishi Bhavan.*
