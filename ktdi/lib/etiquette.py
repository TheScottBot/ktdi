"""The /etiquette dictionary: the situations people ask about, in today's words, filed under the 1860s manuals'
topics, so "texting" finds the rules for letters and "D&D" finds the rules for cards. No AI: matched with the same
loose word matching as /cure (ktdi/lib/cure.py: any word order, small typos).
"""

from ktdi.lib import cure as lookup

# topic: what people might type. The topic names are the tags in ktdi/lib/etiquette.json.
SITUATIONS = {
    "introductions": "introductions | introducing people | being introduced | meeting someone new | meeting new people | "
                     "meeting the parents | meeting the in-laws | first impressions | networking | handshake | "
                     "shaking hands | names | forgetting someone's name",
    "visiting": "visiting | visits | popping round | dropping by | calling on someone | morning call | unannounced visit | "
                "phone call | phoning | ringing someone | facetime | video call | knocking | doorbell | leaving",
    "conversation": "conversation | talking | chatting | small talk | arguing | arguments | debate | gossip | swearing | "
                    "interrupting | jokes | telling jokes | banter | politics | oversharing | voice chat | discord | "
                    "group chat | bragging | boasting | complaining | compliments | being boring | puns | first date | "
                    "going on a date",
    "letters": "letters | writing a letter | texting | text message | texts | email | emails | replying | "
               "left on read | dms | direct messages | whatsapp | thank you note | apology | apologising | "
               "handwriting | spelling",
    "invitations": "invitations | inviting someone | invite | rsvp | being invited | declining an invitation | "
                   "cancelling plans | flaking | plans",
    "street": "the street | walking | in public | out and about | bumping into someone | waving | saying hello | "
              "umbrella | crossing the road | pavement | shopping | queueing | queue",
    "dress": "dress | clothes | outfit | what to wear | fashion | hat | hats | jewellery | cologne | perfume | hair | "
             "beard | shoes | gloves | suit | dress code",
    "parties": "parties | party | house party | birthday | birthday party | gathering | hosting | being a host | "
               "evening party | social | games night | game night",
    "dinner": "dinner | eating | food | table manners | restaurant | takeaway | cutlery | eating with your mouth open | "
              "soup | napkin | burping | dinner party | lunch | breakfast | sharing food | seconds",
    "drinking": "drinking | the pub | pub | bar | beer | wine | getting drunk | drunk | toast | hangover | rounds | "
                "buying a round | cocktails",
    "dancing": "dancing | dance | club | nightclub | ball | asking someone to dance | prom | disco",
    "guest": "staying over | sleepover | house guest | staying at a friend's | staying with friends | airbnb | "
             "guest room | overstaying your welcome | hosting guests",
    "travel": "travel | travelling | train | bus | plane | flight | holiday | road trip | commute | taxi | uber | "
              "public transport | carriage | seats",
    "riding": "riding | horse | horses | driving | cycling | bike | car",
    "smoking": "smoking | vaping | cigarettes | cigar | pipe | tobacco",
    "games": "games | gaming | cards | card games | board games | d&d | dnd | dungeons and dragons | chess | "
             "video games | losing | losing at games | cheating | poker | gambling | betting",
    "sport": "sport | sports | gym | exercise | football | cricket | swimming | fishing | hunting | running | "
             "boxing | fencing",
    "church": "church | wedding | funeral | christening | sermon",
    "theatre": "theatre | cinema | movie | film | movie night | concert | gig | opera | the theatre | talking in a film",
    "home": "home | family | parents | partner | housemates | flatmates | roommates | neighbours | chores | "
            "children | servants | household",
    "money": "money | borrowing money | lending money | paying | splitting the bill | tipping | debt | gifts | "
             "presents | being skint | rich | wealth",
    "general": "general | manners | being polite | politeness | rudeness | being rude | behaviour | being late | "
               "punctuality | life | etiquette | how to behave | being a gentleman | being a lady | tact",
}


def _names(topic: str) -> list[str]:
    return [name.strip() for name in SITUATIONS[topic].split("|") if name.strip()]


INDEX = [(topic, name, tuple(lookup.words(name))) for topic in SITUATIONS for name in _names(topic)
         if lookup.words(name)]


def find_topic(situation: str) -> tuple[str, bool] | None:
    """The topic a situation's filed under, and whether it was asked for by one of its exact names. None if the
    manuals have nothing that fits."""
    found = lookup.best_match(situation, INDEX, spelling=0.85)  # Short names: "dave" isn't "dance"
    return (found[0], found[2]) if found else None


def suggestions(typed: str, limit: int = 25) -> list[str]:
    names = [name for _, name, _ in INDEX]
    return lookup.starting_first(typed, names, limit) if typed.strip() else names[:limit]
