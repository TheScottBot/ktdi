# ktdi
Keep The Degenerates Inline

A tiny Discord bot for keeping your friends in line. Commands work as slash commands (`/spray`) and as text commands using a configurable prefix (`!spray` by default; set `COMMAND_PREFIX` in `.env`).

## Commands

Grouped the same way as `/help`.

### 💦 Rap sheet

| Command | What it does |
|---|---|
| `spray [@user]` | Posts a spray bottle GIF. Target someone to add to their rap sheet. |
| React 💦 | Reacting 💦 to any message sprays whoever sent it and adds to their rap sheet. |
| `rapsheet [@user]` | Shows someone's sprays, times they've been bad, expunges, bails, Don orders, sprays covered by insurance, bribes, committee spending, called predictions, bingo wins and spray futures (defaults to you). |
| `whospray` | Asks the server's Don (set with `/settings whospray_user`) who should be sprayed, with a random phrase. Only the Don is pinged. |
| `tdoi` | The Don Ordered It: sprays yourself, on the Don's orders. Counts as a spray, and as a separate "sprayed themselves on the Don's orders" count on your rap sheet. |
| `blame [reason]` | Blames a random person who's spoken recently in the channel. |
| `bribe <amount>` | Only the person last blamed in the channel can use it. Pays to put the blame back on whoever blamed them (who can then bribe it back). Bribe totals go on the rap sheet. |
| `expunge <amount>` | Pay the committee to remove one spray from your own rap sheet. Only works if you have a spray to remove. The payment counts as a bribe (toward your bribe total, the 👑 and the Champion Briber role), and your rap sheet shows how many you've had expunged. |
| `bail <@user> <amount>` | The counterpart to `expunge`: pay to remove one spray from **someone else's** rap sheet (if you think it was unfair). The payment counts as your bribe. Both rap sheets show it: "Bailed out of N sprays by others" and "Bailed others out N times". |
| `sprayfutures <@user> [stake] [hours]` | Bet that someone gets sprayed within `hours` (1 to 24, default 1), staking 1 to 10 sprays (default 1) per hour. On the line: stake × hours, plus the day's spray interest rate, rounded (e.g. 2 sprays × 3 hours at 15% = 7); the rate is fixed when you bet. The moment someone **other than you** sprays them (`spray`, a 💦 reaction, even `tdoi`), you win and that comes off your rap sheet (never below a clean record). If the time runs out, you lose and it goes on. Spraying them yourself doesn't count, you can't bet on yourself, and it's one open bet per person you're betting on. The result is announced where you bet, and bets survive a restart. |
| `sprayrate` | Today's spray interest rate: a whole number from 1 to 20%, picked each day at `SPRAY_RATE_TIME` in `.env` (default midnight, in `BOT_TIMEZONE`). One rate for the whole bot. |
| `insurance buy / status / complain` | Spray insurance, sold by the committee. `buy` costs $1,000 (paid to the committee, and counted as a bribe) for 2:00 to 9:59 of cover, announced publicly; buying again replaces your policy, no refund. While you're covered, sprays, `bad` and `badbonk` still happen (and sprays still pay out spray futures), but none of it goes on your rap sheet, which counts what insurance covered instead. `status [@user]` shows when a policy runs out, by the car clock. The catch: the committee runs two clocks. The **microwave** decides claims; the **car** clock is the countdown you're shown, and it's up to 20% out either way. Nobody announces when the real cover ends: you find out when a spray lands. `complain` gets you customer service. Neither clock is random: both come from your user ID and the UTC minute you buy (the sums are in `ktdi/lib/insurance.py`), so the same person buying at the same minute always gets the same cover. Working out your best minute, or someone else's worst, is the game. |
| `committee funds / spend / ledger / propose` | The committee's money. Every `bribe`, `expunge`, `bail` and `insurance buy` pays in (including ones from before it kept accounts). `funds` (or just `!committee`) shows the balance and recent spending; anyone can `spend <amount> <item>`, but not more than it has, and it goes on the `ledger` and their rap sheet; `propose` suggests something to argue about, and how many the funds would buy. Shared servers share one committee. |
| `bad [@user]` | Bad. Posts a random non-violent telling-off GIF (from `BAD_GIF_URLS` in `ktdi/features/fun.py`), optionally at someone, which goes on their rap sheet as "Has been bad N times" (separate from sprays), unless `insurance` covers them. |
| `badbonk [@user]` | The violent version of `bad`: a random GIF from `BADBONK_GIF_URLS`. Counts as being bad on the rap sheet, the same as `bad`. |

**Optional Champion Briber role:** if a server has a role named `Champion Briber`, the bot gives it to that server's biggest all-time briber after each bribe (and takes it off the previous holder). The bot needs **Manage Roles**, and its own role must sit above `Champion Briber` in the role list. Servers without the role, or where the bot lacks permission, are skipped. Change the name with `BRIBER_ROLE_NAME`.

### 🎲 Fun

| Command | What it does |
|---|---|
| `loot` | Declares you're looting the body (posts the perception check GIF). |
| `wars [number]` | The KTDI War Archives. 4 or more sprays (including 💦), `bad`s and `badbonk`s at other people in one channel within 5 minutes is a conflict: a **war** if 2 or more people were at it, or a **special military operation** if it was one person on a spree (until someone fires back, which makes it a war). Nobody's told while it's happening. Once nobody's done anything for 10 minutes, the committee suddenly publishes an official historical report in that channel: a gloriously disproportionate title drawn from what happened (wars: "The First Great Badening" for one fought mostly with `bad`, "The Incident at 21:47", "The Friday Night Massacre", "The Siege of Dave's Dignity", "The War of Twenty-Three Poor Decisions"; operations: "Sarah's Special Military Operation", "The Annexation of Dave", "The Unprovoked Incursion at 21:47", "The Sarah Doctrine"), when and how long, hostilities, belligerents, casualties (hits insurance didn't cover), the cause, the most aggressive (or commanding officer) and most persecuted, anyone who never fired back, the arsenal, the outcome and its historical significance. `wars` lists the archives (⚔️ wars, 🪖 operations); `wars 3` shows one in full. Insults (`vulgartongue insult`) count as hostilities too, but they're only words: a burst without at least 4 sprays and bads in it is a **diplomatic incident** (📨), its status set by how many insults flew, from "Diplomatic relations are tense" through "Ambassadors have been recalled" and "Diplomatic relations have broken down" to "A cold war has been declared". It's named after the insults that flew ("The Captain Queernabs Affair") and its report names the most offensive envoy, the most insulted and the words exchanged; insults flung during a real war show in its arsenal. Conflicts stay in their channel, even on servers that share state. Spraying yourself (`tdoi`) doesn't count. The archives only go back to when this was added: sprays weren't timestamped before. |
| `linux` | Asks our resident Linux hater (`LINUX_HATER_ID` in `.env`) a random question about how much they hate Linux. Only they are pinged. |
| `anime` | Asks our resident anime watcher (`ANIME_USER_ID` in `.env`) what they think of a random popular anime from [AniList](https://anilist.co), with a random question. Only they are pinged. If AniList is down it picks from a built-in list. |

### 📚 Words & wisdom

Old dictionaries, idioms, slang, manners and gloom, from books old enough to be out of copyright, and sometimes out of their minds. Each reply's title links to the exact spot in the book (and in a list of entries, each entry's name links to its own): Project Gutenberg pages scroll to the passage and highlight it (in most browsers), and archive.org scans open at the page with the word highlighted.

| Command | What it does |
|---|---|
| `devils [word]` | Ambrose Bierce's cynical definition of a word, from *The Devil's Dictionary* (1911, public domain, via Project Gutenberg): **bore** (a person who talks when you wish him to listen), **lawyer** (one skilled in circumvention of the law), **reason** (to weigh probabilities in the scales of desire)... with his verse and asides, and the made-up poets he credits them to. On its own it's a random entry; `devils <word>` looks one up (typos are fine, and the slash version autocompletes), or, for a word he didn't define, lists the entries that use it (`devils money`). Very long entries are cut short, with the rest a click away. Typed, `!devil` and `!devilsdictionary` work too. Bierce is cruel to everyone, which is the point, but entries that are racist, sexist or mock disability beyond that were read and taken out; only what was kept is recorded (an allowlist, `ktdi/lib/devils_curation.json`), and a test checks the rest stays out using fingerprints. To add an entry, read it in the book, add its headword to that file and run `python -m ktdi.tools.devils_build`. |
| `phrase [idiom]` | Where an idiom comes from, according to the Rev. E. Cobham Brewer's *Dictionary of Phrase and Fable* (1898, public domain, via archive.org), who was very sure of himself: **mad as a hatter**, **to let the cat out of the bag**, **to rain cats and dogs**... Word it however you like (`phrase raining cats and dogs` finds "To rain cats and dogs"; typos are fine and the slash version autocompletes); for a word that isn't an idiom it lists the idioms that mention it (`phrase secret`). On its own it's a random one. Typed, `!idiom` and `!brewer` work too. About 1,800 idioms were hand-picked from the scan's OCR into `ktdi/lib/phrases.json` and mended against the page (Brewer's thousands of gods, saints and poets are left out, and so is anything that punches down), each linked to its page in the scan. |
| `vulgartongue lookup [word]` / `vulgartongue random` / `vulgartongue insult <@user>` | Regency slang from Francis Grose's *Dictionary of the Vulgar Tongue* (1811, public domain, via Project Gutenberg). `vulgartongue insult @dave` insults Dave with a random 1811 insult, pinging only him (enough of them in a channel is a diplomatic incident: see `wars`) ("@Scott has insulted @Dave, in the words of 1811: **Captain Queernabs!** A shabby ill-dressed fellow"; also **Admiral of the Narrow Seas**, **Grinagog**, **Knight of the Trencher**...). `vulgartongue lookup <word>` looks a word up (typos and word order are fine, and the slash version autocompletes), or, for a plain word, finds the slang for it: `drunk` gives Grose's entry plus a dozen other ways to say it, `coward` lists the 1811 words for a coward. Handy for NPC dialogue. `vulgartongue random` (or `lookup` with no word) is a random phrase, never an insult. Typed, `!vt drunk` (or `!vulgartongue`, or `!slang`) looks it up and `!vt` on its own is a random phrase; in the slash menu, `/vt` finds it. Every slur, and every entry that's sexist, racist, xenophobic, homophobic or transphobic, about sex, or mocking disability or bodies, has been taken out, by word list and then entry by entry. Only what was kept is recorded (an allowlist, `ktdi/lib/slang_curation.json`, which also picks the insults), so nothing that was taken out is in the repo; a test checks it stays out using fingerprints, not the words. To add an entry, read it in the book, add its headword to that file and run `python -m ktdi.tools.slang_build`. |
| `deadword [word]` | A word English has stopped using, from Charles Mackay's *Lost Beauties of the English Language* (1874, public domain, via archive.org), a book written to bring them back: **bever** (a drink between meals), **bell-penny** (money laid up to pay for your own funeral)... with Mackay's definition, a line showing it in use, and an epitaph. On its own it's a random one; `deadword <word>` looks one up (typos are fine, and the slash version autocompletes), or, for a plain word, finds the dead words that meant it (`deadword drink`). The words were hand-picked into `ktdi/lib/deadwords.json`: only ones that are really dead now (Mackay also championed words that recovered), with nothing that demeans anyone. |
| `etiquette gentleman [situation]` / `etiquette gentlewoman [situation]` / `etiquette gentlethem [situation]` / `etiquette remind <@user>` | What an 1860s etiquette manual says to do, word for word, from *Routledge's Manual of Etiquette* and Cecil Hartley's *The Gentlemen's Book of Etiquette* (public domain, via Project Gutenberg). `gentleman` gives a rule written for gentlemen, `gentlewoman` one written for ladies, and `gentlethem` one for anyone at all (never one that says he, she, gentleman or lady). Ask about anything, today's situations included: `texting` gets the rules for letters, `D&D` the rules for cards, `the pub`, `splitting the bill`, `talking during a film`, `vaping`... (matched loosely, no AI, from `ktdi/lib/etiquette.py`; the slash versions autocomplete). If the manuals have nothing, the committee offers the nearest thing with a shrug. No situation: any rule. `etiquette remind @dave` reminds Dave of the rules, publicly, pinging only him. The rules were hand-picked into `ktdi/lib/etiquette.json`, leaving out anything demeaning to women, racist or mocking disability; the snobbery stays. Typed, `!etiquette gentlemen dinner` works, and `!etiquette dinner` is gentlethem's. |
| `enquire [anything]` | The Victorian answer to anything, from *Enquire Within Upon Everything* (1856, public domain, via Project Gutenberg), the internet before the internet: how to light a candle, choose a mackerel, play whist or chess, fold a nightcap for travelling. Ask about anything (typos are fine, and the slash version autocompletes); if the book has several hints on it you get one and it says how many more there are. On its own it's a random hint. Typed, `!enquirewithin` and `!ewue` work too. About 1,650 hints; the book's medical, poisoning, cosmetic, vermin-killing and chemistry topics are left out whole (`/cure` has the remedies), and the rest was read with anything dangerous to follow, racist or cruel taken out. Only what was kept is recorded (`ktdi/lib/enquire_curation.json`, by number and title). To add one, read it in the book, add it to that file and run `python -m ktdi.tools.enquire_build`. |
| `melancholy [topic]` | Robert Burton's *The Anatomy of Melancholy* (1621, public domain, via Project Gutenberg): a passage of his gloomy, learned, digressive wisdom on whatever's getting you down: love, study, sleep, idleness, jealousy, poverty, bad air, tobacco ("divine, rare, superexcellent tobacco..."). The passage comes from a part of the book about it (under Burton's own subsection title, "Bad Air, a cause of Melancholy"), or one that mentions it; ask again for another. On its own it's a random one. The topic autocompletes with his subsection titles. Typed, `!burton` and `!gloom` work too. About 510 excerpts, picked by hand word for word (no remedies, nothing on suicide, nothing racist, misogynist or cruel); the build checks every one is in the book exactly as written (`ktdi/lib/melancholy_curation.json`). To add one, copy a few sentences from the book (without the footnote marks) into that file under its subsection and run `python -m ktdi.tools.melancholy_build`. |

### 🔮 Old oddities

Dreams, almanacs, herbs, witches and Mrs Beeton, from the same kind of books, linked the same way.

| Command | What it does |
|---|---|
| `dream [thing]` | What your dream foretells, from Gustavus Hindman Miller's *Ten Thousand Dreams Interpreted* (1901, public domain, via Project Gutenberg): "To dream of an eel is good if you can maintain your grip on him." Give it the thing (`dream eels`) or the whole dream (`dream I dreamt all my teeth fell out` finds teeth; `dream I was lost in a cave` finds caves); typos are fine and the slash version autocompletes. For something Miller didn't cover, it lists the dreams that mention it (`dream landlord`). On its own it's a random dream. Very long entries are cut short, with the rest a click away. About 2,200 dreams; the committee accepts no liability. Entries that are racist, about sex, cruel about disability or about violence against women were read and taken out ("for a young woman to dream of..." stays: that's the joke). Only what was kept is recorded (`ktdi/lib/dream_curation.json`), and a test checks the rest stays out using fingerprints. To add an entry, read it in the book, add its headword to that file and run `python -m ktdi.tools.dream_build`. |
| `almanac [date]` | Today (or any day: `almanac 5 november`, `almanac 25/12`, `almanac tomorrow`) as William Hone's *Every-Day Book* (1826-27, public domain, via Project Gutenberg) has it: the day's saints, a passage on its customs, folklore or history (Hertfordshire's "ganging-day", April Fools' tricks with shoe buckles and "pigeon's milk", the druids' mistletoe), its flower ("Holly. *Ilex aquifolium*", dedicated to its saint), and London's average temperature for it in 1797-1816, in °F and °C. Ask again for another passage: most days have two or three. 29 February has nothing, as neither 1825 nor 1826 had one. Typed, `!onthisday` and `!hone` work too. About 620 passages, picked by hand as the best for their day (and nothing gruesome, racist or cruel); only their keys are recorded (`ktdi/lib/almanac_curation.json`). To add one, read it in the book, add its key to that file and run `python -m ktdi.tools.almanac_build`. |
| `herbal` | Wisdom from a 1531 herbal, the *Tacuini sanitatis*: a random box from its grids, as badly OCR'd by archive.org and translated by Google Translate, with the original cell cropped from the scan. React ⛏️ to dig: each dig is one translation worse (round-tripped through Japanese, Zulu, Finnish, then Korean), down to 🪨 bedrock, the Latin as the scanner read it. The bot takes your ⛏️ back off so you can dig again (needs Manage Messages; otherwise un-react and react). Needs `ktdi/lib/herbal.json` (see Herbal below). |
| `hammeredofwitches` | A witch-finding tip from the *Malleus Maleficarum* (1486), "the Hammer of Witches", which reads like someone hammered wrote it, in Montague Summers' 1928 translation (public domain): how to spot a witch, and the book's wilder lore, linked to its page on archive.org. 45 tips picked by hand into `ktdi/lib/malleus.json`; the book's torture, execution and child-harm passages are left out, and a test keeps it that way. |
| `beeton recipe [dish]` / `beeton advice [topic]` | Mrs Beeton's *Book of Household Management* (1861, public domain, via Project Gutenberg), and the recipes really work. `beeton recipe almond soup` gives her ingredients, method, time, cost (in 1861 money: "2s. 3d. per quart"), when it's in season and how many it serves, often with her aside on where the food comes from; ask for an ingredient (`beeton recipe eels`) and you get one recipe with it and the rest named. No dish: a random one, for when nobody can decide what's for dinner. `beeton advice servants` is her advice on running a house: early rising, servants, dinner parties, wills (not the nursery or the doctor: `/cure` has that). Typos are fine and the dish autocompletes. Typed, `!beeton toad in the hole` is a recipe, and `!beeton` on its own a random one. About 1,250 recipes and 500 passages of advice; asides and advice that are racist or cruel, or that would hurt someone who followed them (cleaning with acid, opiates for teething babies), were read and taken out. Only paragraph numbers are recorded (`ktdi/lib/beeton_curation.json`). To add one, read it in the book, add its number to that file and run `python -m ktdi.tools.beeton_build`. |
| `cure <ailment>` | Nicholas Culpeper's remedy from his *Complete Herbal* (1653, public domain, via Project Gutenberg) for whatever ails you: about 90 ailments from a cold to a missing arm, being cursed and death. It understands how people actually say things ("tickly throat", "my throat is tickly", "the runs", "can't get it up", typos like "diarhea") with a hand-built synonym list, no AI (`ktdi/lib/ailments.py`), and says what it filed yours under. Anything it can't place gets All-heal. The slash version autocompletes. To change which of Culpeper's words count for an ailment, edit its `culpeper` terms there and run `python -m ktdi.tools.cure_build`. |
| `plant <name>` | The other way round: look up one of Culpeper's 320 herbs by any name he gives it ("ground ivy", "piss-a-beds") or its Latin name ("Glechoma hederacea"), and see its Latin name, the planet he puts it under, everything on `/cure`'s list he says it's good for, and one of his remedies. Typos are fine and the slash version autocompletes. The Latin names were checked by hand (`ktdi/lib/herb_latin.json`), and a few herbs Culpeper doesn't pin down are left without one. After editing that file, run `python -m ktdi.tools.cure_build` again. |

### 🎬 Movie night

Everything here except `shhh` is under `/nowplaying`, to keep the rest of the slash menu short. Typed, it's `!nowplaying` or just `!np` (e.g. `!np start`).

| Command | What it does |
|---|---|
| `nowplaying set <title>` | Lines a film up without starting it, so people can `predict` and get their `bingo` cards. Autocompletes from the watchlist, and `Alien` finds `Alien (1979)` if there's only one. `/nowplaying` on its own shows what's on and how far in. |
| `nowplaying start` | Always counts down: it posts a live Discord timestamp ("starts in 5 seconds") that counts itself down on everyone's screen to the same moment, then changes to GO and starts the film (and sets the bot's status to "Watching …"), so everyone presses play together. `!np countdown` still works as another name for it. |
| `nowplaying pause [reason]` / `nowplaying resume` | Pauses don't count towards the time watched (pause over 5 minutes and the committee notices). Both give the exact spot (`0:47:12`) so everyone can line up. Start, resume and `/nowplaying` show a live clock Discord keeps ticking ("⏱️ Started 47 minutes ago", not counting pauses). |
| `nowplaying elapsed` | Only you see it: the exact spot now plus a catch-up point ("skip to 0:47:22, pause, and press play in 10 seconds"), so someone who paused on their own can rejoin in sync. |
| `nowplaying sct <time>` | Set current time, for when the bot's clock is wrong (the film was restarted, or started without the bot): `1:07:30`, `47:30`, `1h 7m`, `47m` or just `47` for minutes. Everything after (the live clock, `elapsed`, pauses, the time watched at the end) follows it, and pause time so far still counts as paused. On a film that's lined up but not started, it starts it at that point. Also `!np seek`. |
| `nowplaying end` | Reveals the predictions and asks for ratings. |
| `nowplaying committeesviews [title]` | The committee's **official viewing report** on the last film watched (or a named one): time watched, rating, morale (from the ratings), predictions upheld, bingo incidents, objections filed and how they were ruled, new canon, plus a committee finding and recommendation (the same each time you ask for that watch). |
| `nowplaying history` / `nowplaying predictions [title]` | What you've watched, with ratings and how many predictions were called; and what was predicted for a film and who called it (e.g. `/nowplaying predictions Alien`, or `Alien #1` for the first watch; it autocompletes). Watching a film again is a new numbered watch ("Alien (watch #2)") with its own predictions, bingo cards and ratings. |
| `nowplaying watchlist [show]` / `add [title] [link]` / `remove <title>` | The to-watch list. `add` a film by title, by Letterboxd link (`link:https://letterboxd.com/film/nosferatu/` adds "Nosferatu (1922)", linked), or both; a link for a film already on the list by title only merges into it, picking up the year and link. `remove` takes a film off (it's kept in the database, just off the list). Films swapped out with `nowplaying set` before they start, or `nowplaying end`ed unstarted, land here too, with their sealed predictions. |
| `nowplaying watchlist import <Letterboxd list>` | Adds every film from a public Letterboxd list (e.g. `https://letterboxd.com/someone/list/halloween-2026/`, or a `boxd.it` link), with years ("Halloween (1978)") and links to each film's Letterboxd page, skipping any already on it. Letterboxd has no open API, so this reads the list's public web page; if Letterboxd changes its pages, `ktdi/lib/letterboxd.py` is the bit to fix. |
| `nowplaying watchlist strike <title>` / `unstrike <title>` | Films watched from the watchlist go back on it struck off when they end; `strike` marks one as watched by hand (e.g. seen elsewhere). Struck films stay on the list, crossed out with the date and at the bottom, and random votes skip them unless they use `include_watched`. `unstrike` undoes it. |
| `nowplaying vote [count] [hours] [include_watched] [films]` / `nowplaying vote end` | Vote on what to watch next: a Discord poll of films from the watchlist, 5 at random by default (`count` up to 10; struck-off films only with `include_watched`), or the ones you name (`films:Alien, Deadstream`). Open until someone runs `nowplaying vote end` (strictly, up to 32 days, Discord's longest poll), or give `hours` for a timed vote. Then the bot announces the winner (ties settled by coin toss) and lines it up, unless a film's already playing. One vote per server at a time. Needs the **Send Polls** permission. |
| `nowplaying rate [1-10]` | Rate the film that's on, or the last one that finished. Shows the group's average, and calls out anyone far enough from everyone else. Without a score, shows everyone's ratings. Rating again replaces your score. |
| `nowplaying predict <guess>` | A sealed prediction about the film: only you see it (`!np predict` deletes your message, if the bot has Manage Messages). `nowplaying end` posts each one; people react ✅/❌ to judge it (not your own). Called predictions go on the rap sheet. Each prediction is saved against its watch of the film; if the film is swapped before it starts, its predictions go to the watchlist with it. |
| `nowplaying bingo card` / `bingo mark <n>` / `bingo unmark <n>` | Movie bingo. Everyone gets their own 5×5 card of film tropes for each film (privately; `!np bingo` sends it by DM). Mark squares as they happen (autocomplete shows your squares); five in a row across, down or diagonally calls BINGO. Wins go on the rap sheet. |
| `nowplaying objection [reason]` | Formally object to a scene, a character's decision or the plot, while it's playing. It's filed at the exact spot (`⚖️ OBJECTION FILED — 0:47:12`) and the committee rules on it: usually overruled, sustained about one time in six. Objections go in the film's `committeesviews` report. |
| `nowplaying canon [claim]` | Propose alternative canon for the film that's on ("Jones the cat is an undercover Weyland-Yutani executive"). Everyone else votes ✅/❌ on the message; more ✅ than ❌ and it's canon. Canon belongs to the title, not the watch: it's read out when the film starts again, so the group's interpretation builds up over rewatches. Without a claim, lists what's canon for the current (or last) film. |
| `shhh [reason]` | A big 🤫 SHHHH telling everyone to be quiet for this bit, naming the film if one's playing, with an optional reason. Pings nobody. |

### 📏 Measurements

| Command | What it does |
|---|---|
| `abm <measurement>` | Anything But Metric: converts a metric measurement (`3cm`, `20C`, `2.5kg`, `100km/h`, `500ml`, `85dB`…) into an absurd unit. Units live in `ktdi/lib/abm_units.json`. |
| `imperial <measurement>` | The sincere version of `abm`: an accurate conversion to imperial/US units (e.g. `180cm` → 5 ft 10.9 in, `75kg` → 165.3 lb (11 st 11.3 lb), `1l` → US and UK pints). Same inputs as `abm`. |

### 💬 Quotes

| Command | What it does |
|---|---|
| `quote add / random / last / show / search / dissociate / claim / delete` | Save and replay things people said. Also: reply to a message with `!quote [@user]` (or `!quote anon`), type `!quote @user what they said -- optional context`, or right-click a message → Apps → **Save quote**. Leaving out the user in `/quote add` (or using `!quote anon`) saves a quote credited to nobody; `dissociate` removes the name (and original-message link) from an existing quote; `claim` lets someone put their own name on an anonymous quote (only ever their own). |

### 🗓️ Campaigns

| Command | What it does |
|---|---|
| `campaign add / show / list / edit / remove` | Keep each campaign's D&D Beyond and VTT links under an alias (`Monday game`, anything you like). `show` gives clickable buttons; aliases autocomplete. `!campaign <alias>` shows one. Only whoever added a campaign, or a mod, can edit or remove it. |
| `campaign remind <alias> <when>` / `campaign unremind <alias>` | Scheduled reminders. The time is when the game starts, plus an optional warning: `mondays at 1900, 15 minutes before`, `monday 7pm 1h before`, `every other friday at 7:30pm from 23 oct, half an hour before`. People react 🔔 to the setup message to get pinged; reminders post the campaign's buttons. Times are in `REMINDER_TIMEZONE` (defaults to `BOT_TIMEZONE`, which defaults to UK time). |
| `campaign skip <alias>` / `campaign reschedule <alias> <change>` | For when things change. `skip` skips the next session (fortnightly games shift a week and carry on from there). `reschedule` takes a new warning (`30 minutes before`), `next 26 oct` (the next session's date) or a whole new schedule. All keep everyone's 🔔. |

### 🔧 Utilities

| Command | What it does |
|---|---|
| `timezone convert [time] [from] [to]` | Convert a time between timezones: `/timezone convert 7pm London New York` → "**19:00** in London (BST) is **14:00** in New York (EDT)", plus the same moment in each reader's own time. Everything's optional but you need a `from` or a `to`: a left-out time is now, and a left-out zone is yours (from `set`), or `BOT_TIMEZONE` if you haven't set one. So `/timezone convert to:Tokyo` is the time in Tokyo now. Zones can be cities, abbreviations (`EST`, `BST`; summer time handled), offsets (`UTC+5:30`) or full names, and autocomplete. Also `!tz`; quote zones with spaces, and use `now` to skip the time: `!tz convert now "New York"`. |
| `weather in [place]` / `weather here` | Today's forecast (from [Open-Meteo](https://open-meteo.com), free, no key): now and today's high and low in °C and °F, chance of rain and wind. Next to it, a saying from Richard Inwards' *Weather Lore* (1893, public domain): one for today's date if there is one (St Swithin's on 15 July), otherwise one about today's weather at this time of year ("A winter fog / Will freeze a dog"), and the committee's view on whether science and folk wisdom agree. `weather in <place>` is for anywhere (add the county where there are several: `Highbridge, Cumbria`); with no place it's `WEATHER_PLACE` in `.env` (default London). **Your own weather, privately:** `weather here` asks where you are in a pop-up form only you see (not a command option: Discord shows those to anyone who hovers over the command), then posts "Scott checked the weather where they are" with your forecast, never saying where. The place is used for that one lookup and kept nowhere: not stored, not cached, not logged (`/weather` is never logged). Typed, it's `!weather here <place>`, and your message is deleted first. If Open-Meteo is down, folk wisdom carries on alone. The sayings were picked and tidied by hand from the archive.org scan into `ktdi/lib/weather_lore.json`; "Folk wisdom" under each one links to its page in the scan, with a word highlighted (never to anything about the forecast or where anyone is). |
| `timezone set <zone>` / `timezone show [@user]` / `timezone clear` | `set` saves your timezone once, for every server; `show` gives your time or someone else's (if they've set theirs); `clear` forgets yours. |
| `books search <query>` / `books download <ID or title>` | Search a Calibre-Web library and download a book (optional; see below). |
| `rpg search <query>` / `rpg download <number or name>` | Search the RPG rulebooks in a Dropbox folder (words from the name or folder, any order: `5e player`) and get a private download link (optional; see below). |
| `settings show` / `settings shared_state <true/false>` / `settings whospray_user [@user]` | Per-server settings, stored in the database. **Shared state** (on by default, needs Manage Server to change) pools quotes, sprays, bribes and campaigns with every other server that has it on; off keeps them local to that server, and switching loses nothing. **whospray_user** chooses the Don, who `/whospray` asks and `/tdoi` obeys (leave it empty to clear); only the user IDs in `WHOSPRAY_ADMIN_IDS` in `.env` can change it, not even server admins. |
| `help [command or section]` | Where to start (`/spray`, `/rapsheet`, `/bad`, `/quote random`, `/nowplaying`) and the sections, a line each, with a menu to open any section: it opens just for you, so anyone can use the menu. `/help old oddities` (or any section's name, loosely) opens a section; `/help abm` (or any command) gives the details, like every unit `/abm` understands. Sections list each command once; a command with subcommands (`/quote …`) lists them on its own page. |

### Notes

Everything the bot remembers (rap sheets, quotes, campaigns, movie nights, the committee's funds…) is in `ktdi.db` (SQLite) next to `bot.py`; set `DB_PATH` to move it. Each row remembers which server it came from, so `/settings shared_state` can pool servers or keep them apart.

Text commands need the **Message Content Intent** enabled on the bot's page in the Developer Portal.

## Setup

1. Create an application and bot at https://discord.com/developers/applications and copy the bot token.
2. Invite the bot to your server using the OAuth2 URL generator with the `bot` and `applications.commands` scopes.
3. Create a virtual environment and install the project (Windows):

   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   pip install -e .
   ```

4. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.
5. Run the bot (with the venv active):

   ```bash
   ktdi
   ```

   or `python bot.py`.

### Library (optional)

`/books` searches a [Calibre-Web](https://github.com/janeczku/calibre-web) server through its OPDS feed and sends books as Discord attachments. To turn it on, set `CALIBRE_URL`, `CALIBRE_USERNAME`, `CALIBRE_PASSWORD` and `BOOKS_GUILD_IDS` in `.env` (see `.env.example`):

- Create a dedicated Calibre-Web user for the bot with only the **download** permission.
- The commands only work, and only appear, in the servers listed in `BOOKS_GUILD_IDS`.
- `/books` replies are only visible to the person who asked; `!books download` sends the file by DM.
- Discord's upload limit (10 MB on unboosted servers) applies. The bot sends the first format in `BOOK_FORMATS` that fits, or says the book is too big.

### RPG rulebooks (optional)

`/rpg` searches a folder of rulebooks in your Dropbox and sends a **private download link** straight from Dropbox (it lasts 4 hours), so big PDFs work: they're usually far over Discord's upload limit. Like `/books`, replies are only visible to the person who asked (`!rpg download` sends the link by DM), and nobody's searches or downloads are logged. To turn it on:

1. Go to https://www.dropbox.com/developers/apps → **Create app** → **Scoped access** → **Full Dropbox** (needed to reach a folder like `Family Room`; the bot only ever reads the folder you give it) → name it, e.g. `KTDI rulebooks`.
2. On the app's **Permissions** tab, tick **files.metadata.read** and **files.content.read** (nothing else) and **Submit**.
3. On the **Settings** tab, copy the **App key** and **App secret**.
4. On your PC, run `python -m ktdi.tools.dropbox_login`, paste the key and secret, open the link it prints, allow the app, and paste back the code. It prints the three `DROPBOX_*` lines for `.env`.
5. In the bot's `.env`, add those, plus the folder as it appears in Dropbox (`https://www.dropbox.com/home/Family%20Room/RPGs` is `/Family Room/RPGs`) and the servers it's for:

   ```
   RPG_DROPBOX_PATH=/Family Room/RPGs
   RPG_GUILD_IDS=111111111111111111
   ```

The commands only work, and only appear, in the servers in `RPG_GUILD_IDS`, and only once every one of these is set. The folder is re-read at most every 10 minutes, so new rulebooks show up within that. The refresh token is like a password for reading your Dropbox: keep `.env` private, and you can revoke it any time under Dropbox → Settings → Connected apps.

### Herbal

`/herbal` posts from `ktdi/lib/herbal.json`, built once from the [1531 *Tacuini sanitatis* on archive.org](https://archive.org/details/bub_gb_9lIU1a_-ddAC). The bad translations are the point, and they come from Google Translate, through Google Sheets (free, no API key):

1. `python -m ktdi.tools.herbal_build extract` reads archive.org's OCR of the book's tables, keeps the cells that look like words (about 600), and writes `herbal-build/herbal_cells.csv` (gitignored), with `GOOGLETRANSLATE` formulas on each row: the translation, then four worse levels for digging.
2. In Google Sheets: **File → Import → Upload** that CSV (**Replace spreadsheet**). Wait until no cell says *Loading…*: it's a few thousand translations, so give it a while (scroll to the bottom right to check), then **File → Download → Comma-separated values**.
3. `python -m ktdi.tools.herbal_build merge` finds that download in your Downloads folder and writes `ktdi/lib/herbal.json`. Commit it, deploy, and `/herbal` is live.

### Logs

The bot logs startup, every command used (except `/books` and `/rpg`, which are never logged against anyone), 💦 sprays, bribes and role changes to `logs/ktdi.log` next to `bot.py` (and to the terminal/journal). The file rotates at 1 MB, keeping 5 old files (`ktdi.log.1` … `ktdi.log.5`). To follow it live:

```bash
tail -f logs/ktdi.log
```

### Dev bot

To try changes in a test server before they go live, create a second bot application, invite it to your test server only, fill in `.env.dev` (gitignored; same keys as `.env.example`) and run:

```bash
python bot.py --dev
```

This loads `.env.dev` instead of `.env`. Give the dev bot a different `COMMAND_PREFIX`, only the test server in `GUILD_IDS`, and its own `DB_PATH`.

If the log says "Couldn't add slash commands to server …" (Discord's *Missing Access*), that server in `GUILD_IDS` either doesn't have the bot in it, or the bot was invited without the `applications.commands` scope. The bot skips it and starts anyway.

Slash commands can take a while to appear or update when registered globally. Set `GUILD_IDS` in `.env` to a comma-separated list of server IDs to register them to those servers only, which updates instantly.

## Project layout

For how it all fits together, conventions, and rules for changes, see [ARCHITECTURE.md](ARCHITECTURE.md).

```
bot.py                 # starts the bot (python bot.py [--dev]); also: python -m ktdi, or the ktdi command
ktdi/
├── bot.py             # the bot: startup, loading features, syncing slash commands, command logging
├── config.py          # settings from .env
├── db.py              # database connection, tables, upgrades, and shared state (scope())
├── common.py          # small helpers shared by features
├── oldbooks.py        # what the 📜 Old books dictionaries share (lookups, autocomplete, the "uses" list)
├── features/          # one file per feature, each a discord.py extension with a setup(bot)
│   ├── fun.py         # spray, whospray, tdoi, loot, bad, badbonk, linux, blame, bribe, expunge, bail, rapsheet, 💦, Champion Briber
│   ├── futures.py     # sprayfutures
│   ├── insurance.py   # insurance
│   ├── wars.py        # wars
│   ├── committee.py   # the committee's funds
│   ├── anime.py       # anime
│   ├── herbal.py      # herbal
│   ├── malleus.py     # hammeredofwitches
│   ├── cure.py        # cure, plant
│   ├── slang.py       # vulgartongue
│   ├── deadword.py    # deadword
│   ├── devils.py      # devils
│   ├── dream.py       # dream
│   ├── phrase.py      # phrase
│   ├── beeton.py      # beeton
│   ├── enquire.py     # enquire
│   ├── almanac.py     # almanac
│   ├── melancholy.py  # melancholy
│   ├── etiquette.py   # etiquette
│   ├── movie.py       # movie night: nowplaying (np), shhh
│   ├── units.py       # abm, imperial
│   ├── weather.py     # weather
│   ├── timezones.py   # timezone
│   ├── quotes.py
│   ├── campaigns.py   # campaigns and reminders
│   ├── settings.py
│   ├── books.py
│   ├── rpg.py         # RPG rulebooks from Dropbox
│   └── help.py        # asks each feature for its HELP_CATEGORY and help_extras(), so new features don't touch it
├── lib/               # no Discord code: unit conversions, reminder schedules, timezones, and the Calibre-Web, Dropbox, Letterboxd and AniList clients
└── tools/             # one-off helpers: dropbox_login, herbal_build, cure_build, slang_build, devils_build, dream_build, beeton_build, enquire_build, almanac_build, melancholy_build, deadword_pages, weather_lore_pages (python -m ktdi.tools.<name>); gutenberg.py is what the Gutenberg builds share
tests/                 # pytest
```

To add a feature: create `ktdi/features/<name>.py` with its commands and an `async def setup(bot)` that registers
them, add it to `FEATURES` in `ktdi/features/__init__.py`, set `HELP_CATEGORY` (where it sits on the `/help` list), and
optionally a `help_extras(command)` for `/help <command>`.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
```

The tests use an in-memory database and fake Discord objects, never your real `.env`, database or token. They cover
every feature, a fake Calibre-Web for `/books` and a fake Dropbox for `/rpg` (including that nothing is logged against a
reader), and that every `/help` page fits Discord's limits.
