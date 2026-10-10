"""The /cure dictionary: every ailment, the many ways people say it, and the words Culpeper used for it in 1653.

`names` are what people might type (matched loosely, typos and word order allowed); the first is the one shown.
`culpeper` are regular expressions for his 17th-century terms ("quinsy", "the flux", "falling sickness"), used by
ktdi/tools/cure_build.py to find the herbal's sentences for each ailment. Each matches as a whole word, so "rest" doesn't
match "restrains"; end one with * to match it as a stem ("sneez*" for sneeze, sneezing...). Change `names` freely;
change `culpeper`, then rebuild (python -m ktdi.tools.cure_build).
"""

import re
from dataclasses import dataclass
from functools import cached_property


@dataclass(frozen=True)
class Ailment:
    names: tuple[str, ...]
    culpeper: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.names[0]

    @cached_property
    def pattern(self) -> re.Pattern:
        """Any of Culpeper's terms, each as a whole word (or, ending in *, as the start of one)."""
        terms = [rf"{term[:-1]}" if term.endswith("*") else rf"{term}\b" for term in self.culpeper]
        return re.compile(r"\b(?:" + "|".join(terms) + ")", re.IGNORECASE)


def ailment(names: str, culpeper: str) -> Ailment:
    """Both lists as "a | b | c", to keep the table below readable."""
    return Ailment(tuple(n.strip() for n in names.split("|")), tuple(c.strip() for c in culpeper.split("|")))


AILMENTS = [
    # --- Colds, coughs and chests ---
    ailment("common cold | cold | colds | the cold | head cold | runny nose | blocked nose | stuffy nose | snotty nose |"
            " sniffles | snot | congestion | catarrh | blocked sinuses | sinusitis | sinuses",
            r"rheums? | catarrh | defluxions? | distillations? | stuffing of the head | coryza | colds\b"),
    # Culpeper never met hay fever. His sneezing herbs cause it (to purge the brain), so it gets his running rheums.
    ailment("hay fever | hayfever | allergies | allergy | pollen | sneezing | sneezes | sneezy",
            r"rheums? | defluxions? | distillations? | rheum in the eyes | watering eyes"),
    ailment("flu | influenza | man flu | the flu | grippe | fluey | flu like | aches and fever | feeling rough |"
            " under the weather | coming down with something | lurgy | the lurgy",
            r"agues? | pestilent fevers? | malignant fevers? | burning fevers?"),
    ailment("fever | high temperature | temperature | running a temperature | burning up | chills | the chills |"
            " shivers | the shivers | shivering | hot and cold | sweats | night sweats",
            r"fevers? | agues? | hot fits | cold fits | shaking fits | quartan | tertian"),
    ailment("cough | coughing | chesty cough | dry cough | hacking cough | tickly cough | whooping cough | coughs |"
            " smokers cough | smoker's cough | phlegm | mucus | coughing up phlegm",
            r"coughs? | chin-cough | phthisick? | phlegm | tough humours of the breast"),
    ailment("sore throat | tickly throat | scratchy throat | itchy throat | throat | strep | strep throat |"
            " tonsillitis | tonsils | swollen glands | hoarse | hoarseness | lost my voice | lost voice | no voice |"
            " laryngitis | croaky | croaky voice | frog in my throat",
            r"sore throats? | quinsy | quinsies | throat | hoarseness | almonds of the ears | uvula"),
    ailment("chest infection | bronchitis | wheezing | wheezy | asthma | short of breath | shortness of breath |"
            " breathless | out of breath | can't breathe | cant breathe | pneumonia | lungs | chest | tight chest",
            r"shortness of breath | short-winded | wheezing | asthma | pleurisy | lungs | breast | difficulty of breathing"),
    ailment("tuberculosis | tb | consumption | wasting disease",
            r"consumptions? | phthisick? | ulcers of the lungs | hectic"),

    # --- Heads and minds ---
    ailment("headache | head ache | migraine | migraines | sore head | splitting headache | my head hurts |"
            " tension headache | brain freeze | head pain | pounding head",
            r"head-?ache | headach* | megrim | pains? (?:of|in) the head | diseases of the head"),
    ailment("hangover | hungover | hung over | drank too much | too much beer | too much wine | the morning after |"
            " booze | drunk | drunkenness | still drunk | beer fear | the horrors",
            r"drunkenness | drunk | surfeit*"),
    ailment("dizziness | dizzy | vertigo | light headed | lightheaded | head spinning | room spinning | fainting |"
            " faint | fainted | passed out | swooning | woozy",
            r"swimming in the head | giddiness | vertigo | swoonings? | faintings? | fainting"),
    ailment("seizures | seizure | fits | epilepsy | convulsions | convulsing",
            r"falling[- ]sickness | convulsions? | fits"),
    ailment("stroke | palsy | paralysis | paralysed | paralyzed | numbness | numb | pins and needles | tremors |"
            " shaking hands | shakes | the shakes | trembling",
            r"palsy | palsies | apoplexy | numbness | trembling | shaking"),
    ailment("forgetfulness | forgetful | memory loss | bad memory | brain fog | can't remember | cant remember |"
            " dementia | senile | absent minded | stupid | stupidity | thick | dim | slow | dumb | idiot | brainless |"
            " no brain cells | lost my keys",
            r"memory | dul+ness | wits | understanding | quicken* the (?:wits|senses)"),
    ailment("madness | insanity | gone mad | going mad | crazy | mental | lunacy | losing it | losing my mind |"
            " lost my mind | frenzy | delirium | hallucinations | seeing things | hearing voices | unhinged",
            r"madness | frenzy | frenzies | frantick? | lunatick? | lunacy | distracted"),
    ailment("melancholy | depression | depressed | sad | sadness | down in the dumps | gloomy | the blues |"
            " miserable | low mood | feeling low | glum | dead inside | bored | boredom | existential dread |"
            " ennui | mopey | moping | the doldrums",
            r"melancholy | melancholick? | sadness | heaviness | mirth | merry | cheerful | sorrow"),
    ailment("anxiety | anxious | stress | stressed | stressed out | worried | worry | nervous | nerves | panic |"
            " panic attack | palpitations | heart racing | on edge | jittery | jumpy | wound up",
            r"trembling of the heart | palpitations? | passions? of the heart | fear | fearfulness | comfort the heart"),
    ailment("heartbreak | broken heart | heartbroken | dumped | got dumped | rejected | lovesick | love sick |"
            " lonely | loneliness | single | being single | forever alone | unrequited love | no girlfriend |"
            " no boyfriend | ghosted | left on read",
            r"passions? of the heart | comfort* the heart | grief | sorrow | (?:causes?|procures?|provokes?) love | love-?(?:potions?|sick)"),
    ailment("insomnia | can't sleep | cant sleep | sleepless | no sleep | not sleeping | restless nights |"
            " awake all night | up all night | sleep",
            r"sleep | procure rest | watchings"),
    ailment("nightmares | nightmare | bad dreams | night terrors | sleep paralysis | the night hag",
            r"night-?mare | the mare | incubus | fearful dreams | dreams"),
    ailment("tiredness | tired | exhausted | exhaustion | fatigue | no energy | lethargic | lethargy | sleepy |"
            " knackered | shattered | wiped out | lazy | laziness | sloth | can't be bothered | cant be bothered |"
            " mondays | monday | jet lag | burnout | burnt out",
            r"weariness | lethargy | drowsiness | sleepiness | heaviness | dul+ness | strengthens? | vital spirits"),
    ailment("anger | angry | rage | raging | temper | bad temper | grumpy | cranky | irritable | hangry | furious |"
            " stroppy | moody | road rage",
            r"choler | cholerick? | anger | wrath | hot humours"),
    ailment("cowardice | coward | cowardly | scared | fear | fearful | frightened | no courage | wimp | wuss |"
            " chicken | spineless",
            r"fear | fearfulness | courage | comfort the heart | faint-?hearted"),

    # --- Eyes, ears, nose and mouth ---
    ailment("sore eyes | eyes | red eyes | pink eye | conjunctivitis | itchy eyes | dry eyes | watery eyes |"
            " bloodshot eyes | stye | styes | eye strain | screen eyes | tired eyes",
            r"sore eyes | (?:red|hot|watering|weeping|blood-?shot|bleared) eyes | blood-?shot |"
            r" (?:inflammations?|pains?|redness|heat|rheum) (?:of|in) the eyes | eyes"),
    ailment("bad eyesight | eyesight | poor eyesight | blurry vision | blurred vision | short sighted | long sighted |"
            " cataracts | cataract | need glasses | squinting | can't read | cant read",
            r"dimness | dim sight | (?:clears?|clearing|quickens?|strengthens?) (?:the )?sight | sight |"
            r" pin and web | films?"),
    ailment("blindness | blind | going blind | can't see | cant see | lost my sight | lost my eyesight",
            r"blindness | (?:been|are|were|is|grown) blind | restored? (?:the )?sight"),  # not "make them blind"
    ailment("earache | ear ache | ear infection | ears | sore ears | earwax | ear wax | blocked ears",
            r"(?:pains?|aches?|swellings?|ulcers?|imposthumes?) (?:in|of) the ears | ears"),
    ailment("deafness | deaf | hard of hearing | can't hear | cant hear | going deaf | hearing loss | tinnitus |"
            " ringing ears | ringing in my ears",
            r"deaf* | noises? (?:in|of) the(?:m| ears) | singings?"),
    ailment("toothache | tooth ache | sore tooth | sore teeth | bad teeth | teeth | cavity | cavities |"
            " rotten teeth | tooth decay | gum disease | gums | bleeding gums | abscess tooth | teething | wisdom teeth",
            r"tooth-?ache | teeth | gums"),
    ailment("bad breath | halitosis | stinky breath | smelly breath | breath smells | morning breath | dragon breath |"
            " garlic breath",
            r"stinking breath | breath"),
    ailment("mouth ulcers | mouth ulcer | ulcers in my mouth | cold sore | cold sores | canker sore | sore mouth |"
            " cracked lips | chapped lips | dry lips | thrush | sore tongue",
            r"sores? in the mouth | ulcers? (?:in|of) the mouth | cankers? | mouth | lips | tongue"),
    ailment("nosebleed | nose bleed | nosebleeds | bloody nose | bleeding nose",
            r"bleeding (?:at|of) the nose | bleedings at the nose | nose"),

    # --- Stomachs and below ---
    ailment("stomach ache | stomachache | tummy ache | belly ache | bellyache | stomach pain | stomach cramps |"
            " gut ache | upset stomach | dodgy tummy | sore stomach | sore tummy | stomach bug | gastro",
            r"stomach | belly | griping | gripings | colick? | cholick?"),
    ailment("indigestion | heartburn | acid reflux | reflux | acid | bloating | bloated | gas | wind | trapped wind |"
            " flatulence | farting | farts | fart | burping | burps | belching | gassy | windy",
            r"wind | windiness | flatulenc[ey] | digestion | concoction | belchings? | heart-burning"),
    ailment("nausea | nauseous | feeling sick | sick | vomiting | throwing up | being sick | puking | spewing |"
            " travel sickness | car sick | carsick | sea sick | seasick | morning sickness | queasy",
            r"vomit | vomiting | sickness of the stomach | loathing of (?:the )?(?:stomach|meat) | casting"),
    ailment("diarrhoea | diarrhea | the runs | the trots | loose stools | upset bowels | dysentery | food poisoning |"
            " the squits | the shits | dodgy kebab | delhi belly | bad curry",
            r"flux | fluxes | lasks? | bloody-flux | dysentery | looseness | scouring"),
    ailment("constipation | constipated | blocked up | backed up | can't poo | cant poo | can't go | haven't been",
            r"costive | costiveness | open (?:the )?belly | purges? | loosens? the belly | stools"),
    ailment("worms | tapeworm | parasites | threadworms | pinworms | roundworm",
            r"worms"),
    ailment("loss of appetite | no appetite | not hungry | always hungry | hunger | the munchies | munchies |"
            " eating too much | overeating | gluttony | greedy | food baby | ate too much | stuffed",
            r"appetite | surfeits? | hunger | gluttony"),
    ailment("weight loss | lose weight | fat | overweight | obese | obesity | chubby | dad bod | beer belly | diet",
            r"fat | corpulen* | lean | gross bodies"),
    ailment("hiccups | hiccup | hiccough | hiccoughs | the hiccups",
            r"hiccoughs? | hiccups? | yexing"),
    ailment("piles | haemorrhoids | hemorrhoids | sore bum | itchy bum | bum problems | sore arse | pain in the arse |"
            " pain in the ass | pain in the butt",
            r"piles | h(?:æ|ae|e)morrhoids | fundament"),
    ailment("jaundice | yellow skin | liver | hepatitis | liver damage | bad liver | cirrhosis",
            r"jaundice | liver"),
    ailment("spleen | splenic", r"spleen"),
    ailment("kidney stones | kidney stone | gallstones | kidneys | kidney",
            r"stone | gravel | reins | kidneys"),
    ailment("bladder problems | bladder | uti | urinary infection | cystitis | peeing a lot | can't pee | cant pee |"
            " painful peeing | burning pee | weak bladder | incontinence",
            r"bladder | strangury | (?:stopping|stoppage|heat|sharpness|scalding|difficulty) of urine |"
            r" (?:provokes?|procures?|stays?) urine | making water | pissing"),

    # --- Skin and hair ---
    ailment("spots | acne | pimples | zits | blackheads | whiteheads | bad skin | breakouts | breaking out",
            r"pimples | pushes | spots | pustules | blemishes | wheals"),
    ailment("complexion | freckles | sunburn | sun burn | sunburnt | tan | sun spots | blotchy skin | ugly |"
            " ugliness | wrinkles | wrinkly | ageing | aging | looking old | beauty | resting bitch face",
            r"freckles | sun-?burning | morphew | complexions? | beautif* | wrinkles | the face"),
    ailment("itch | itchy | itching | rash | rashes | eczema | dermatitis | hives | scabies | prickly heat | psoriasis | athletes foot |"
            " athlete's foot | fungal infection | jock itch | ringworm",
            r"itch | scabs? | tetters? | ring-?worms? | manginess | scurf"),
    ailment("warts | wart | verrucas | verruca | corns | corn | bunions | moles | skin tags",
            r"warts | corns"),
    ailment("burns | burn | burnt | burned | scald | scalds | scalded | burnt myself | burned myself | on fire |"
            " spontaneous combustion | burnt tongue",
            r"burnings? | burns | scaldings? | scalds | fire"),
    ailment("bruises | bruise | bruised | black eye | bump | bumps | lump on my head | knocked | sprain | sprained |"
            " sprained ankle | twisted ankle | swelling | swollen | rolled ankle |"
            " stubbed toe | stubbed my toe | banged my head | hit my head",
            r"bruises | bruised | sprains? | swellings | blows | falls"),
    ailment("cuts | cut | wound | wounds | graze | grazes | scrape | gash | bleeding | paper cut | papercut |"
            " stabbed | stab wound | knife wound | sliced my finger | splinter",
            r"wounds | green wounds | cuts | (?:stays?|stops?|stanch\w*) (?:the )?bleeding | bleedings | thorns | splinters"),
    ailment("broken bones | broken bone | fracture | fractured | broken arm | broken leg | broken wrist |"
            " broken finger | broken toe | broken nose | broken rib | dislocated | dislocation",
            r"broken bones | bones | fractures | knits? | joints? out of place | displaced"),
    ailment("missing limb | missing an arm | lost an arm | missing arm | no arm | no arms | missing a leg |"
            " missing leg | lost a leg | no legs | amputation | amputated | lost a finger | missing finger |"
            " lost a toe | chopped off | cut off | fell off | beheaded | decapitated | lost my head | missing head",
            r"cut sinews | sinews (?:that are )?cut | consolidat* | members out of joint | joints? out of (?:joint|place)"),
    ailment("ulcers | ulcer | sores | open sore | boils | boil | abscess | abscesses | cyst | cysts | infected |"
            " infection | pus | carbuncle | fistula",
            r"ulcers | sores | imposthumes? | boils | biles | fistulas? | felons | carbuncles?"),
    ailment("hair loss | bald | baldness | balding | going bald | receding hairline | thinning hair |"
            " losing my hair | alopecia | bald patch",
            r"hair | baldness | falling of the hair"),
    ailment("dandruff | flaky scalp | itchy scalp | nits | head lice | lice | fleas",
            r"dandriff | dandruff | scurf | lice | nits | fleas"),
    ailment("body odour | body odor | bo | b o | smelly | stinky | stink | sweaty | sweating | smelly feet |"
            " stinky feet | cheesy feet | smelly armpits | pong | whiffy",
            r"sweat | sweats | stinking | rank smell | ill scent"),
    ailment("chilblains | cold hands | cold feet | frostbite | chapped hands | dry skin | cracked skin |"
            " cracked heels | rough skin",
            r"kibes | chilblains | chaps | chapped | roughness of the skin"),
    ailment("blisters | blister", r"blisters | blistered"),
    ailment("sore feet | aching feet | foot pain | feet | tired feet",
            r"feet"),

    # --- Aches, joints and backs ---
    ailment("gout | gouty", r"gout"),
    ailment("joint pain | arthritis | sore joints | stiff joints | rheumatism | aching joints | knee pain |"
            " bad knees | dodgy knee | creaky | creaky joints | stiff neck | crick in my neck | neck pain",
            r"joints | aches | pains of the joints | stiffness | stiff"),
    ailment("back pain | bad back | sore back | backache | back ache | lower back pain | slipped disc | sciatica |"
            " put my back out | hip pain",
            r"sciatica | pains? in the back | the back | hip-gout | loins | hips"),
    ailment("cramp | cramps | muscle cramp | leg cramp | charley horse | spasms | spasm | stitch",
            r"cramps? | convulsions | shrinking of the sinews"),
    ailment("aches and pains | aching | aches | sore muscles | muscle pain | pulled muscle | sore all over |"
            " doms | leg day | gym",
            r"aches | pains | sinews"),

    # --- Hearts and blood ---
    ailment("heart problems | heart disease | heart | chest pain | high blood pressure | blood pressure | angina",
            r"(?:panting|beating|trembling|tremblings|weakness|pains?|passions?) of the heart | cordial | vital spirits"),
    ailment("heavy bleeding | haemorrhage | hemorrhage | coughing up blood | spitting blood | blood loss",
            r"spitting of blood | bleeding | issues of blood | stanch | stay blood"),
    ailment("weakness | weak | anaemia | anemia | pale | pasty | frail | feeble | wasting away | too thin |"
            " skinny | puny | no muscles",
            r"weakness | weak | green-?sickness | pale | strength | strengthen"),
    ailment("water retention | swollen legs | swollen ankles | oedema | edema | fluid retention | dropsy |"
            " cankles",
            r"dropsy | dropsies | swellings"),

    # --- Bites, poisons and plagues ---
    ailment("insect bites | insect bite | bug bites | bug bite | mosquito bites | mosquito bite | midge bites |"
            " bee sting | wasp sting | stings | sting | stung | horsefly",
            r"stinging | stings | bitings? | venomous | bees | wasps | hornets"),
    ailment("snake bite | snakebite | adder bite | bitten by a snake | viper",
            r"adders? | serpents? | vipers? | venomous beasts"),
    ailment("dog bite | bitten by a dog | rabies | mad dog | rabid",
            r"mad dogs? | biting of a mad dog"),
    ailment("poisoning | poisoned | poison | toxic | toxins | detox | ate something bad",
            r"poisons? | venom | venomous | antidote"),
    ailment("plague | the plague | black death | pandemic | covid | coronavirus | pestilence | epidemic",
            r"plague | pestilence | pestilential"),
    ailment("smallpox | small pox | measles | chickenpox | chicken pox | spotty fever",
            r"small-?pox | measles"),
    ailment("syphilis | the clap | std | stds | sti | stis | venereal disease | french pox | the pox",
            r"french-?pox | venereal"),
    ailment("scrofula | kings evil | king's evil", r"king['’]?s-? ?evil"),
    ailment("cancer | tumour | tumor | tumours | lump | lumps | growth | growths",
            r"cancers? | tumours? | hard swellings | kernels"),
    ailment("leprosy | leper", r"leprosy | lepers?"),
    ailment("hernia | rupture | ruptures | ruptured", r"ruptures? | burstings? | burstenness"),
    ailment("scurvy", r"scurvy"),
    ailment("rickets", r"rickets"),

    # --- Bodies and babies ---
    ailment("period pain | periods | period | menstrual cramps | pms | heavy period | heavy periods | late period |"
            " time of the month | period cramps | on the blob",
            r"terms | courses | menses | women'?s courses"),
    ailment("pregnancy | pregnant | labour | labor | childbirth | giving birth | in labour | contractions",
            r"birth | delivery | travail | women in labour"),
    ailment("infertility | infertile | trying for a baby | can't get pregnant | cant get pregnant | barren",
            r"barrenness | barren | conception | conceive | fruitful"),
    ailment("low libido | no sex drive | sex drive | impotence | impotent | erectile dysfunction | can't get it up |"
            " cant get it up | horny | too horny | lust | lustful | frisky | randy",
            r"venery | lust | venereal | stir up lust | provokes? venery"),
    ailment("breastfeeding | milk supply | sore nipples | nipples | lactation",
            r"(?:increases?|breeds?|procures?|brings?|dries? up) (?:the )?milk | milk in (?:nurses|women) | nurses | paps"),

    # --- Beyond medicine ---
    ailment("cursed | curse | bewitched | hexed | witchcraft | jinxed | bad luck | unlucky | evil eye | haunted |"
            " ghosts | ghost | possessed | demons | demon | demonic possession | witches | werewolf | vampire |"
            " zombie | the devil",
            r"witchcraft | bewitched | evil spirits | devils? | charms | enchantments"),
    ailment("death | dead | dying | died | deceased | i died | being dead | immortality | live forever | old age |"
            " getting old | mortality | the void",
            r"prolong* | old age | youth | saved life | preserves? life | length of days | long life"),
]
