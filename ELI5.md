

## The big idea

Houston streets kill and injure a lot of people. The city's current way of
finding dangerous streets is basically: **look at where crashes already
happened, and call those spots dangerous.** That works, but it has a blind
spot — it can only react *after* people have been hurt. A street can be built
in a way that's obviously dangerous and still look "fine" on the map simply
because the crashes haven't piled up there *yet*.

We're building the other approach: **figure out what makes a street dangerous
by its design** (how wide it is, how many lanes, how fast traffic moves,
whether there are crosswalks) and then flag *every* street with those risky
features — even ones that haven't had a bad crash recorded yet. Think of it as
the difference between waiting for people to get sick (reactive) versus
noticing the unsafe conditions that *will* make people sick (proactive).

The big question at the end: **how many dangerous streets does the city's
"wait for crashes" method miss that our "look at the design" method catches?**

Why this matters specially in Texas: a lot of cities make streets safer with
red-light and speed cameras. **Texas banned those.** So Houston can't enforce
its way to safety — it has to *design* its way there. That makes "which streets
are dangerously designed?" not just interesting, but the main lever the city
actually has.

We started in one slice of Houston — **City Council District C** (the inner-loop
area: Heights, Montrose, Museum District, Meyerland, Braeswood), in partnership
with that district's council office.

> **Update — we've now scaled this up to the entire City of Houston.** Once the
> whole process worked for District C, expanding was mostly a matter of swapping
> in the city's outline and re-running everything. The story below was written as
> we built District C step by step (so it still says "District C" in places), but
> the **current maps and numbers now cover all ~75,000 city street segments**, not
> just the one district. The citywide toll is at the end.

---

## Where we are right now

Before you can study streets, you need a clean, accurate list of them. That
sounds trivial. It is not. **Everything we've done so far is building that
list** — a trustworthy map of every street in District C, chopped into pieces,
with what we know about each piece. No crash analysis yet; that comes once the
crash data arrives. We've been laying the foundation the whole house sits on.

Here's the story of how we built it, step by step.

### Step 1 — Draw the boundary
We grabbed the official, up-to-date outline of District C straight from the
city's own map service. (Houston redrew these district lines a couple years
ago, so we made sure to get the *current* one — we double-checked by confirming
it lists the right council member.) This is our fence: everything inside it is
our study area.

### Step 2 — Get every street
We pulled every street inside that fence from OpenStreetMap (think Wikipedia,
but for maps — free and very detailed). Then we threw out the things that
aren't "city streets we care about":
- **Freeways and highway ramps** — the *state* controls those, not the city, so
  the city can't redesign them. Out.
- **Frontage/feeder roads** (the access roads running alongside freeways) —
  same deal, they're part of the highway and belong to the state. Out.
- **Alleys and driveways** — not real through-streets. Out.

What's left is the street network the *city* can actually do something about.

### Step 3 — Cut streets into "blocks"
A whole street like Westheimer is too big to study as one thing — it's
dangerous in some stretches and calm in others. So we cut every street into
**segments**: the piece of road between one intersection and the next. One
block, basically. That's our basic unit — the thing we'll eventually score for
danger. We ended up with thousands of these little pieces.

### Step 4 — Write down what we know about each block
For every segment we recorded what the map data told us: how many lanes, the
posted speed limit, whether it's one-way, whether there's a sidewalk or bike
lane, whether the intersections at its ends have traffic signals, and so on.

Here's an honest catch we found and wrote down: the map data is **patchy**.
Number of lanes? Known for ~85% of streets — great. Speed limit? Only ~14%.
Street width? Basically zero. Importantly, "we don't know" is *not* the same as
"it's not there" — a missing sidewalk in the data usually just means nobody
typed it in, not that the sidewalk doesn't exist. We're tracking exactly how
complete each piece of information is, so we never fool ourselves later. The
missing stuff we'll fill in from other sources (city and state datasets) down
the road.

### Step 5 — Fix the divided-road double-counting
Big streets with a grassy median or median strip (like Memorial or Heights
Boulevard) are stored in the map as **two separate one-way streets** — the
eastbound side and the westbound side — even though it's really one road. If we
left that alone, our analysis would see Memorial Drive *twice*, each as a
skinny half-street, and get confused about how busy and how wide it really is.

So we taught the computer to spot these pairs (same name, running right next to
each other in opposite directions) and **glue each pair back into one street**,
adding up the lanes so the combined street has the right size. We did this
carefully and kept a record of every piece we moved, so nothing's lost and we
can always check our work. This cleaned up about a quarter of the road mileage.

### Step 6 — Throw out the junk scraps
Slicing streets at every intersection leaves behind tiny, meaningless scraps —
little stubs of turn lanes, or the few feet of a cross-street that pass through
a median. These aren't real "blocks" and would muddy the analysis. We sorted
the short pieces into three buckets:
- **Turn lanes / slip roads** → not real streets, removed (but saved in a
  side list, not deleted forever).
- **Little bits of real, named streets** → these *are* real road, just chopped
  badly, so we **glued them onto the proper street** they belong to.
- **Tiny unnamed nameless fragments** → junk, removed.

We were deliberately cautious: if a short piece might be a real street, we kept
it. After this, the network is clean — no more confusing scraps.

### Keeping everything honest and shareable
Alongside the street-building, we set up the habit stuff so this project stays
trustworthy and isn't a black box:
- **An interactive Street Explorer — live on the web** at
  https://wrenvin.github.io/PharisFellowshipVisionZero/ (no software needed,
  just open the link). You can **color the streets by anything** (traffic,
  speed, lanes, income…), **filter** to just the streets you care about — e.g.
  "show me wide, fast streets with no sidewalk," which instantly highlights the
  most worrying streets — **search** for a street by name, and **click any
  street** to pin a panel with everything we know about it. It's the seed of
  the public dashboard the project will grow into.
- **Four documents we keep updated:** the README (quick facts), the LOG (a
  dated diary of every decision and *why*), the CODEBOOK (what every piece of
  data means), and this ELI5.
- **Everything saved to GitHub** after each step, so there's a full history and
  nothing can get lost.

---

## What's next

The streets are ready, and we've started **filling in the blanks** — adding
facts about each street from the city's own datasets.

**Just done: speed limits.** We found the City of Houston's official speed-limit
data and matched it onto our streets. A real-world wrinkle we handled honestly:
Houston only formally posts speed limits on its *bigger* streets. Most
neighborhood streets aren't individually posted — but Texas law says any city
street without a posted sign is automatically 30 mph. So we used the city's real
numbers where they exist and the legal 30-mph default everywhere else, and we
*labeled every street with where its number came from*, so we never confuse "the
city measured this" with "the law says it's this." Every street now has a speed.

**Also just done: lanes, width, and medians.** That same city dataset told us,
for each street, how many lanes it has, how wide the pavement is, and whether
it has a median (a raised divider, a center turn lane, or nothing). Two nice
wins here: street *width* was completely blank before — now it's filled in for
99% of streets. And the city's median info independently confirmed the
divided-road fix we did earlier (the streets we'd flagged as divided really are
divided). As always, we labeled where every number came from — the city's
measurement, or a sensible default for small neighborhood streets.

**Also just done: traffic volume.** We added how many cars use each street per
day (the city measures this with road sensors). This matters a lot: a wide,
fast street isn't automatically "more dangerous" if barely anyone drives it —
you have to account for how many people are actually exposed. The city measures
traffic at a few hundred spots across the district, so we have real numbers for
nearly all the *big* streets (98%) and fewer of the small residential ones —
which is fine, because the big streets are where the danger is. We were careful
*not* to make up numbers for streets with no count; we'd rather leave a blank
than guess. (Bonus: the same sensors also recorded how fast cars *actually*
drive — not just the posted limit — which will matter a lot later.)

**Also just done: neighborhood demographics.** We added, for each street, who
lives in its neighborhood — income, poverty rate, racial makeup, and how many
households don't own a car (from the U.S. Census). Two reasons this matters:
fairness (are dangerous streets concentrated in poorer or less-white
neighborhoods?), and accuracy (a neighborhood where lots of people don't own
cars has more people walking, which changes the risk picture). One honest
caveat we wrote down: the Census reports this by *neighborhood*, not by street,
so every street in a neighborhood gets that neighborhood's numbers — it's
background context, not a fact about one specific block.

**Also just done: sidewalks.** For each street we worked out whether it has a
sidewalk on both sides, one side, or none. Surprising hurdle: **Houston has no
official map of where its sidewalks are** — so we used OpenStreetMap, where
volunteers have actually drawn about 344 miles of District C sidewalks. We
matched those to each street and figured out which side(s) they're on (and we
widened the search for big roads, since their sidewalks sit farther from the
center). About 56% of streets have a sidewalk on at least one side; 44% have
none mapped. Big honest caveat, same as before: "none" means "none drawn in the
map," which is strong evidence of a gap but not a guarantee — so we'll treat it
carefully, especially since missing sidewalks are part of the danger story.

**Also just done: land use.** For each street we worked out what's around it —
homes, shops/offices, industry, parks, etc. — using the county's property
records. Streets lined with shops and businesses behave differently (more cars
turning in and out, more people on foot) than quiet residential blocks, so this
helps the model compare fairly. About 79% of streets got a clear answer; the
rest are roads running through big places with no individual lots — Hermann
Park, Rice University, the Medical Center, the bayou trails — and we left those
honestly blank rather than guess.

**That completes the street profiles.** Every street in District C now has its
full design + context fingerprint: size, speed, traffic, sidewalks, median,
land use, and neighborhood. The foundation is built.

**The crash data has arrived** — the location-stamped records of where people
have actually been hurt (state crash files for 2016–2025, plus a partial 2026).
We cleaned it up and kept the crashes on **streets** (not freeways). The one
clear cut: we drop limited-access freeways and tollways (I-610, US-59, the
Sam Houston Tollway), because those are a different kind of road, the state runs
them, and crashes on them tend to get mis-pinned onto the city street running
underneath. But we **keep the at-grade big streets even when the state owns
them** — like Highway 6, S Main / US-90A, and Westheimer (which out west is
officially the state's FM 1093). That's deliberate: this is how Austin's Vision
Zero dashboard and Houston's own High Injury Network do it, because a huge share
of the deaths happen on exactly those state-owned arterials, and ignoring them
would hide the problem. The decade's toll on city streets: **1,687 people killed
and 9,928 killed or seriously injured** (about **69,500 years of life lost**).

What we *do* do is **label** every street and crash as city-owned or
state-owned (TxDOT), so the dashboard can say plainly that about **1 in 6 of the
serious crashes on these streets are on state-owned arterials** — the ones the
City can't fix alone and has to push TxDOT to redesign. (If you also counted the
freeways we leave out, state-owned roads are closer to half of all the city's
serious crashes.) That's an honest, useful point rather than quietly dropping
those roads. (Running just District C earlier gave 88 killed
and 712 injured; the whole city is far larger.)

We then figured out **which crashes involved people walking or biking** (the
crash records list everyone involved, so we flagged any crash with a pedestrian
or cyclist). The finding is sobering and important: people on foot or bike are
only **2% of crashes but about a third of the deaths** — they're rarely in
crashes, but when they are, it's far more likely to be fatal. That's exactly
why this project focuses on street *design*.

Then we **connected each crash to its street**: we matched every crash to the
nearest street (within about 200 feet, which absorbs the small errors in where
crashes get pinned on a map), so now every street block carries its own crash
tally — total crashes, severe crashes, and pedestrian/bike crashes. We
double-checked that every crash got counted exactly once, and the streets that
came out worst (Memorial, Westheimer, Montrose, Kirby…) are exactly the ones
Houston already knows are dangerous — a reassuring sign we did it right. Telling
detail: **93% of street blocks have had zero severe crashes** — which is the
whole reason the city's "wait for crashes" approach has blind spots, and why our
design-based approach can help.

The crash data is now **on the live map** too: you can color the streets by how
many crashes (or severe crashes, or pedestrian crashes) each has had, filter to
just the streets with a serious crash, and click any street to see its crash
history. The picture is stark — most streets are grey (no severe crashes), and a
handful of big roads light up red. That grey-vs-red map is basically the city's
current "where crashes happened" view — and it's exactly what our design-based
model will be compared against.

We also built a **second, public-friendly dashboard focused purely on safety**
(a "Vision Zero" view, alongside the data-explorer one). Instead of letting you
browse every kind of data, it leads with what matters: how many people have been
killed or seriously hurt, **how many years of life that lost** (a powerful way to
show a young person's death counts for more than the bare number "1"), *which*
streets carry almost all of that harm (just 6% of streets account for ~71% of it citywide),
a switch to focus on a single travel mode (everyone, driving, walking, or biking),
and breakdowns of who's being hurt (in a vehicle vs. walking vs. biking), of when
it happens **by time of day**, and **by year — and you can click a year to break
it down into that year's twelve months**. There's also a switch
between shaded streets and individual crash dots, and the city's own official
"most dangerous streets" list (its High Injury Network) laid over the top for
comparison. It's modeled on how cities like Austin and New York present their
traffic-safety data to the public — it shows what has actually happened, and
stays out of conclusions we haven't proven yet.

Next: build the model that answers the project's real question — **which
dangerous streets is the city's current crash-only method missing?**

---

*Plain-language companion to README.md (facts), LOG.md (decisions/diary), and
CODEBOOK.md (data dictionary). Updated alongside them.*
