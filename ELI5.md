# ELI5 — What We're Doing, In Plain English

A no-jargon tour of this project. If you've never opened the code, start here.
(README = the facts, LOG = the diary, CODEBOOK = the dictionary, **ELI5 = the story.**)

---

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

We're doing all of this for one slice of Houston — **City Council District C**
(the inner-loop area: Heights, Montrose, Museum District, Meyerland, Braeswood)
— in partnership with that district's council office.

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
- **A map you can actually read** — open `reports/network_map.html` in a
  browser. It color-codes streets by type, has a plain-English legend, and lets
  you hover any street to see its details in normal words.
- **Four documents we keep updated:** the README (quick facts), the LOG (a
  dated diary of every decision and *why*), the CODEBOOK (what every piece of
  data means), and this ELI5.
- **Everything saved to GitHub** after each step, so there's a full history and
  nothing can get lost.

---

## What's next

The streets are ready. The two things still coming:
1. **The crash data.** The detailed, location-stamped crash records live with
   the state (TxDOT) and need special government access — the council office is
   helping get District C's slice. This is the one piece we're waiting on.
2. **Filling in the blanks.** Traffic volume (how many cars use each street),
   real speed limits, sidewalks, land use, neighborhood demographics — pulled
   from city and state datasets to complete each street's profile.

Once those land, we connect crashes to streets, build the model that learns
"what does a dangerous street look like," and finally answer the headline
question: **which dangerous streets is the city's current method missing?**

---

*Plain-language companion to README.md (facts), LOG.md (decisions/diary), and
CODEBOOK.md (data dictionary). Updated alongside them.*
