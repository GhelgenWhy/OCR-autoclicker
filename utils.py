# -*- coding: utf-8 -*-
"""
Утилиты для автокликера.
Содержит логику скачивания/загрузки словаря английских слов и подбора анаграмм.
"""

import os
import urllib.request
import urllib.parse
import re
import collections
from typing import List, Set, Dict, Tuple
import config

# Кэш ответов уровней, чтобы не запрашивать повторно
_level_cache: Dict[int, List[str]] = {}
_search_cache: Dict[str, Tuple[List[str], int]] = {}

# Ссылка для скачивания Scrabble словаря английских слов (~267 000 слов, включая "afro")
DICTIONARY_URL = "https://raw.githubusercontent.com/jesstess/Scrabble/master/scrabble/sowpods.txt"

# Базовый встроенный словарь на случай отсутствия интернета
FALLBACK_WORDS = [
    "act", "add", "age", "aim", "air", "art", "ash", "ask", "bad", "bag", "bar", "bat", "bed", "bee", "beg", "bet",
    "big", "bin", "bit", "bow", "box", "boy", "bus", "but", "bye", "cab", "can", "cap", "car", "cat", "cow", "cry",
    "cup", "cut", "day", "did", "die", "dig", "dim", "dog", "dot", "dry", "due", "ear", "eat", "end", "era", "eye",
    "fan", "far", "fat", "few", "fit", "fix", "fly", "fog", "for", "fox", "fry", "fun", "fur", "gas", "gem", "get",
    "god", "gun", "guy", "gym", "hat", "her", "hey", "him", "his", "hit", "hop", "hot", "how", "hub", "hug", "ice",
    "ill", "ink", "its", "ivy", "jar", "jaw", "job", "joy", "key", "kid", "kit", "lab", "lap", "law", "lay", "leg",
    "let", "lid", "lie", "lip", "log", "low", "mad", "man", "map", "mat", "max", "may", "men", "met", "mix", "mud",
    "mug", "net", "new", "nil", "nod", "not", "now", "nut", "oak", "odd", "off", "oil", "old", "one", "our", "out",
    "own", "pad", "pan", "pat", "pay", "pen", "pet", "pig", "pin", "pit", "pot", "pro", "pub", "pun", "put", "rag",
    "ram", "ran", "rat", "raw", "red", "rib", "rid", "rig", "rim", "rip", "rob", "rod", "rot", "row", "rub", "rug",
    "rum", "run", "sad", "saw", "say", "sea", "see", "set", "sew", "she", "shy", "sin", "sip", "sir", "sit", "six",
    "ski", "sky", "sly", "sob", "sod", "son", "soy", "spa", "spy", "sub", "sue", "sun", "tag", "tan", "tap", "tax",
    "tea", "ten", "the", "thy", "tie", "tin", "tip", "toe", "ton", "too", "toy", "try", "tub", "two", "use", "van",
    "vet", "via", "war", "was", "wax", "way", "web", "wed", "wet", "who", "why", "wig", "win", "wit", "won", "woo",
    "yes", "yet", "you", "zoo",
    "able", "acid", "also", "area", "army", "away", "baby", "back", "band", "bank", "base", "bear", "beat", "beer",
    "bell", "belt", "best", "bike", "bill", "bird", "blow", "blue", "boat", "body", "bold", "bone", "book", "boom",
    "born", "boss", "both", "bowl", "bulk", "burn", "bush", "busy", "cake", "call", "calm", "camp", "card", "care",
    "case", "cast", "cave", "cell", "cent", "chat", "chef", "city", "clay", "clip", "club", "coal", "coat", "code",
    "cold", "cook", "cool", "cope", "copy", "cord", "core", "cork", "cost", "crew", "crop", "cure", "cute", "dare",
    "dark", "data", "date", "dawn", "days", "dead", "deal", "dear", "debt", "deep", "deer", "desk", "dial", "diet",
    "dirt", "disc", "dish", "disk", "does", "done", "doom", "door", "dose", "down", "draw", "drew", "drop", "drug",
    "drum", "dual", "duck", "due", "duke", "dust", "duty", "each", "earn", "ease", "east", "easy", "echo", "edge",
    "else", "envy", "epic", "even", "ever", "exam", "exit", "face", "fact", "fade", "fail", "fair", "fake", "fall",
    "fame", "fare", "farm", "fast", "fate", "fear", "feat", "feed", "feel", "fees", "feet", "felt", "file", "fill",
    "film", "find", "fine", "fire", "firm", "fish", "fist", "five", "flat", "fled", "flee", "flow", "foam", "focus",
    "fold", "folk", "fond", "food", "fool", "foot", "ford", "fore", "form", "fort", "foto", "four", "free", "frog",
    "from", "fuel", "full", "fund", "fuse", "game", "gang", "gate", "gave", "gear", "gene", "gift", "girl", "give",
    "glad", "glow", "goal", "goat", "gold", "golf", "gone", "good", "gray", "grew", "grey", "grid", "grin", "grip",
    "grow", "gulf", "hair", "half", "hall", "halo", "hand", "hang", "hard", "hate", "have", "hawk", "head", "hear",
    "heat", "held", "hell", "help", "hero", "hers", "hide", "high", "hill", "hint", "hire", "hold", "hole", "holy",
    "home", "hope", "horn", "hose", "host", "hour", "huge", "hung", "hunt", "hurt", "icon", "idea", "idle", "inch",
    "into", "iron", "item", "jack", "jade", "jail", "java", "jazz", "join", "joke", "jolt", "jump", "jury", "just",
    "keen", "keep", "kept", "keys", "kick", "kids", "kill", "kind", "king", "kiss", "knee", "knew", "knit", "knot",
    "know", "labs", "lace", "lack", "lady", "laid", "lake", "lamb", "lamp", "land", "lane", "last", "late", "lawn",
    "lazy", "lead", "leaf", "leak", "lean", "leap", "left", "legs", "lend", "lens", "less", "lest", "liar", "lick",
    "life", "lift", "like", "limb", "lime", "line", "link", "lion", "lips", "list", "live", "load", "loan", "lobe",
    "lock", "loft", "logo", "logs", "long", "look", "loom", "loop", "lord", "lose", "loss", "lost", "lots", "loud",
    "love", "luck", "lung", "lush", "made", "mail", "main", "make", "male", "mall", "many", "maple", "maps", "mark",
    "mask", "mass", "mate", "math", "meal", "mean", "meat", "meet", "melt", "memo", "menu", "mess", "meta", "mice",
    "mild", "mile", "milk", "mill", "mind", "mine", "mini", "mint", "miss", "mist", "mode", "mold", "mole", "mono",
    "mood", "moon", "more", "most", "move", "much", "must", "mute", "myth", "nail", "name", "near", "neat", "neck",
    "need", "neon", "nest", "news", "next", "nice", "niche", "nine", "node", "noon", "nose", "note", "noun", "nude",
    "oath", "obey", "odds", "odor", "okay", "once", "only", "onto", "open", "oral", "ours", "oval", "oven", "over",
    "pace", "pack", "page", "pain", "pair", "pale", "palm", "pant", "papa", "para", "park", "part", "pass", "past",
    "path", "pave", "peak", "pear", "peas", "peel", "peer", "pelt", "penn", "pent", "pest", "pets", "pick", "pile",
    "pill", "pine", "pink", "pins", "pint", "pipe", "pity", "plan", "play", "plea", "plot", "plug", "plum", "plus",
    "poem", "poet", "poke", "pole", "poll", "polo", "pond", "pool", "poor", "pope", "port", "pose", "post", "pour",
    "pray", "prep", "prey", "punk", "pure", "push", "quad", "rage", "raid", "rain", "ramp", "rank", "rare", "rate",
    "read", "real", "rear", "rebel", "rector", "refit", "regal", "reign", "relax", "relic", "remit", "renal", "renew",
    "repay", "resin", "retch", "retro", "retry", "reuse", "revil", "rhino", "rhyme", "rider", "ridge", "rifle",
    "right", "rigid", "riley", "rinse", "ripen", "risen", "riser", "river", "rivet", "roach", "roady", "roast", "robin",
    "robot", "robust", "rodeo", "roger", "rogue", "roman", "rondo", "rough", "round", "route", "rover", "rowdy",
    "royal", "rugby", "ruler", "rumor", "rural", "rusty", "saber", "sadly", "safari", "safer", "salad", "salon",
    "salsa", "salty", "salve", "samba", "sandy", "satin", "sauce", "sauna", "saver", "savoy", "scale", "scalp",
    "scaly", "scamp", "scant", "scare", "scarf", "scary", "scene", "scent", "scoff", "scold", "scoop", "scope",
    "scorn", "scout", "scowl", "scram", "scrap", "scree", "screw", "scrub", "scuba", "scuff", "scull", "scute",
    "seamy", "sedan", "seedy", "seism", "seize", "selah", "selfy", "semen", "semis", "senna", "senor", "sense",
    "sepal", "sepia", "septa", "serif", "serge", "serum", "serve", "servo", "setup", "seven", "sever", "sewer",
    "shack", "shade", "shady", "shaft", "shaky", "shale", "shall", "shame", "shamp", "shank", "shape", "shard",
    "share", "shark", "sharp", "shave", "shawl", "sheaf", "shear", "sheen", "sheep", "sheer", "sheet", "shelf",
    "shell", "shied", "shier", "shift", "shill", "shine", "shiny", "ships", "shire", "shirk", "shirr", "shirt",
    "shish", "shoal", "shock", "shoes", "shone", "shook", "shoot", "shore", "shorn", "short", "shout", "shove",
    "shown", "showy", "shred", "shrew", "shrub", "shrug", "shuck", "shun", "shunt", "shush", "shut", "shyly",
    "sibil", "sible", "sicca", "sicko", "sided", "sides", "sidle", "siege", "sieve", "sifty", "sighs", "sight",
    "sigma", "silky", "sills", "silty", "silly", "silva", "since", "sinew", "singe", "sinks", "sinus", "siren",
    "sissy", "sitar", "sites", "sixes", "sixth", "sixty", "sized", "sizer", "sizes", "skate", "skeet", "skein",
    "skews", "skids", "skied", "skier", "skies", "skiff", "skill", "skimp", "skims", "skink", "skins", "skint",
    "skips", "skirt", "skits", "skive", "skoal", "skua", "skulk", "skull", "skunk", "skyey", "slab", "slack",
    "slags", "slain", "slake", "slams", "slang", "slant", "slaps", "slash", "slate", "slats", "slaty", "slave",
    "slaws", "slays", "sleds", "sleek", "sleep", "sleet", "slept", "slice", "slick", "slide", "slier", "slily",
    "slime", "slimy", "sling", "slink", "slips", "slits", "sliver", "slob", "sloe", "slog", "sloop", "slope",
    "slops", "slosh", "sloth", "slots", "slows", "sludge", "sludgy", "slued", "slues", "slugs", "slump", "slums",
    "slung", "slunk", "slur", "slurp", "slush", "slushy", "sluts", "slyly", "smack", "small", "smart", "smash",
    "smear", "smell", "smelt", "smile", "smirk", "smite", "smith", "smock", "smog", "smoke", "smoky", "smote",
    "smut", "snack", "snafu", "snag", "snail", "snake", "snaky", "snap", "snare", "snarl", "sneak", "sneer",
    "snick", "snide", "sniff", "snipe", "snips", "snitch", "snob", "snood", "snoop", "snoot", "snore", "snort",
    "snot", "snout", "snowy", "snub", "snuff", "soak", "soap", "soapy", "soar", "sober", "sock", "soda", "sofa",
    "soft", "softy", "soil", "solar", "sold", "sole", "solid", "solo", "solve", "some", "song", "soon", "soot",
    "sore", "sort", "soul", "sound", "soup", "sour", "south", "sown", "space", "spade", "span", "spare", "spark",
    "spas", "spat", "spawn", "speak", "spec", "speed", "spell", "spend", "spent", "sperm", "spew", "sphere",
    "spice", "spicy", "spied", "spiel", "spier", "spies", "spike", "spiky", "spill", "spilt", "spina", "spine",
    "spiny", "spire", "spirt", "spit", "spite", "spits", "spitz", "splat", "splay", "split", "spoil", "spoke",
    "spoof", "spook", "spool", "spoon", "spoor", "spore", "sport", "spots", "spout", "sprat", "spray", "spree",
    "sprig", "sprit", "sprog", "spud", "spue", "spume", "spumy", "spun", "spunk", "spurn", "spurt", "sputa",
    "squad", "squat", "squaw", "squib", "squid", "stab", "stack", "staff", "stage", "stags", "stagy", "staid",
    "stain", "stair", "stake", "stale", "stalk", "stall", "stamp", "stand", "stane", "stang", "stank", "staph",
    "stare", "stark", "stars", "start", "stash", "state", "stats", "stave", "stays", "stead", "steak", "steal",
    "steam", "steed", "steel", "steep", "steer", "stein", "stela", "stele", "stem", "steno", "steps", "stere",
    "stern", "stets", "stews", "stick", "stied", "sties", "stiff", "stile", "still", "stilt", "sting", "stink",
    "stint", "stipe", "stirk", "stirp", "stirs", "stoat", "stock", "stoic", "stoke", "stole", "stoma", "stomp",
    "stone", "stony", "stood", "stool", "stoop", "stope", "stops", "store", "stork", "storm", "story", "stoup",
    "stout", "stove", "stow", "strap", "straw", "stray", "strep", "strew", "stria", "strip", "strop", "strow",
    "strum", "strut", "stub", "stuck", "stud", "study", "stuff", "stull", "stum", "stump", "stung", "stunk",
    "stunt", "stupa", "stupe", "sturt", "styed", "styes", "style", "styli", "suave", "subas", "suber", "such",
    "suck", "sudor", "suds", "sued", "suede", "suer", "sues", "suet", "suety", "sugar", "suing", "suite", "suits",
    "sulci", "sulfa", "sulfo", "sulky", "sully", "sumac", "summa", "sumps", "sunny", "sunup", "super", "supra",
    "surah", "sural", "suras", "surd", "sure", "surf", "surge", "surfy", "surly", "sushi", "sutra", "swab",
    "swad", "swag", "swain", "swale", "swam", "swamp", "swamy", "swan", "swank", "swap", "sward", "sware",
    "swarf", "swarm", "swart", "swash", "swat", "swath", "sway", "swear", "sweat", "sweaty", "sweep", "sweet",
    "swell", "swelt", "swept", "swift", "swig", "swill", "swim", "swine", "swing", "swink", "swipe", "swirl",
    "swish", "swiss", "swive", "swob", "swol", "swon", "swoop", "swop", "sword", "swore", "sworn", "swum",
    "swung", "sycee", "syces", "sycite", "syke", "syles", "sylva", "symar", "synch", "syncs", "synds", "synod",
    "syrah", "syren", "syria", "syrup", "tabby", "table", "taboo", "tabor", "tacit", "tack", "tacky", "taco",
    "tact", "taffy", "tail", "take", "talc", "tale", "talk", "tall", "tame", "tang", "tank", "tape", "taps",
    "target", "task", "taste", "tasty", "team", "tear", "tech", "teem", "teen", "teeth", "tell", "temp", "tend",
    "tent", "term", "test", "text", "than", "that", "them", "then", "they", "thin", "this", "thou", "thus",
    "tick", "tide", "tidy", "tied", "tier", "tile", "till", "time", "tiny", "tips", "tire", "toad", "today",
    "toes", "toll", "tone", "tong", "tony", "took", "tool", "toot", "topic", "tops", "torn", "toss", "tour",
    "town", "toxic", "toys", "trace", "track", "tract", "trade", "trail", "train", "trait", "tray", "tree",
    "trek", "trend", "trial", "tribe", "trick", "trim", "trio", "trip", "true", "tube", "tuck", "tuft", "tune",
    "turn", "twin", "type", "ugly", "uncle", "under", "undo", "unit", "unto", "upon", "urge", "used", "user",
    "utmost", "vague", "vain", "valet", "valid", "value", "valve", "vapor", "vary", "vase", "vast", "vault",
    "vein", "veldt", "venom", "venue", "verb", "verge", "verse", "very", "vessel", "vest", "veto", "via", "vial",
    "vibe", "vice", "video", "view", "vigor", "villa", "vinyl", "viola", "viral", "virus", "visit", "visor",
    "vista", "visual", "vital", "vivid", "vocal", "vodka", "vogue", "voice", "void", "volt", "volume", "vote",
    "vow", "wade", "wafer", "wager", "wages", "wagon", "waist", "wait", "wake", "walk", "wall", "waltz", "wand",
    "want", "ward", "warm", "warn", "warp", "wash", "wasp", "waste", "watch", "water", "wave", "wavy", "weak",
    "wealth", "wear", "weary", "weave", "web", "wed", "weed", "week", "weep", "weigh", "weird", "weld", "well",
    "went", "were", "west", "wet", "what", "wheel", "when", "where", "which", "while", "whip", "whir", "whiskey",
    "white", "whole", "whom", "whose", "why", "wide", "widow", "width", "wife", "wild", "will", "wind", "wine",
    "wing", "wink", "winner", "winter", "wipe", "wire", "wiry", "wise", "wish", "wit", "witch", "with", "witty",
    "wizard", "woad", "woke", "wolf", "woman", "womb", "women", "won", "wood", "wool", "word", "work", "world",
    "worm", "worn", "worry", "worse", "worst", "worth", "would", "wound", "woven", "wrap", "wrath", "wreak",
    "wreck", "wren", "wrest", "wring", "wrist", "write", "wrong", "wrote", "wrung", "yacht", "yard", "yarn",
    "yawn", "yeah", "year", "yeast", "yell", "yellow", "yelp", "yield", "yoke", "yolk", "young", "your", "youth",
    "zeal", "zebra", "zenith", "zero", "zest", "zinc", "zone", "zoom"
]

def load_dictionary() -> Set[str]:
    """
    Загружает словарь слов. Если файл words.txt отсутствует или содержит мало слов (< 20000),
    пытается скачать его из сети (Scrabble словарь ~83k слов).
    Если скачивание не удалось (нет интернета), возвращает базовый встроенный словарь.
    Также динамически расширяет словарь формами множественного числа на -s.
    """
    words = set()
    should_download = False
    
    # 1. Попытка загрузить из локального файла
    if os.path.exists(config.WORDS_FILE):
        print(f"[*] Загрузка словаря из локального файла: {config.WORDS_FILE}")
        try:
            with open(config.WORDS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w.isalpha() and len(w) >= 3:
                        words.add(w)
            if len(words) < 150000 or "afro" not in words:
                print(f"[*] Локальный словарь устарел или слишком мал ({len(words)} слов). Будет скачан расширенный словарь SOWPODS.")
                should_download = True
                words.clear()
            else:
                print(f"[+] Успешно загружено {len(words)} слов из локального файла.")
        except Exception as e:
            print(f"[!] Ошибка чтения локального файла словаря: {e}")
            should_download = True
    else:
        should_download = True
        
    # 2. Попытка скачать из интернета
    if should_download:
        print(f"[*] Скачивание расширенного Scrabble-словаря по адресу: {DICTIONARY_URL}")
        try:
            req = urllib.request.Request(
                DICTIONARY_URL, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode('utf-8')
                for line in content.splitlines():
                    w = line.strip().lower()
                    if w.isalpha() and len(w) >= 3:
                        words.add(w)
                        
            # Сохраняем скачанный словарь локально для будущих запусков
            with open(config.WORDS_FILE, "w", encoding="utf-8") as f:
                for w in sorted(words):
                    f.write(w + "\n")
                    
            print(f"[+] Расширенный словарь успешно скачан и сохранен ({len(words)} слов).")
        except Exception as e:
            print(f"[!] Не удалось скачать расширенный словарь ({e}). Используем локальный/встроенный.")
            # Если не удалось скачать, но у нас был какой-то локальный словарь, перезагрузим его
            if os.path.exists(config.WORDS_FILE):
                try:
                    with open(config.WORDS_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            w = line.strip().lower()
                            if w.isalpha() and len(w) >= 3:
                                words.add(w)
                except Exception:
                    pass

    # 3. Использование резервного словаря, если вообще ничего не загрузилось
    if not words:
        words = set(w.lower() for w in FALLBACK_WORDS if len(w) >= 3)
        print(f"[+] Загружен встроенный словарь ({len(words)} слов).")

    # 4. Динамическое добавление форм множественного числа / 3-го лица глаголов на -s
    # Это позволяет боту вводить слова, которые отсутствуют в словарях в явном виде
    extended_words = set(words)
    for w in words:
        # Стандартные правила образования множественного числа в английском
        if w.endswith(('s', 'x', 'z', 'ch', 'sh')):
            extended_words.add(w + 'es')
        elif w.endswith('y') and len(w) > 1 and w[-2] not in 'aeiou':
            extended_words.add(w[:-1] + 'ies')
        else:
            extended_words.add(w + 's')
            
    print(f"[+] Словарь расширен формами на -s/es/ies с {len(words)} до {len(extended_words)} слов.")
    return extended_words


def solve_anagrams(letters: List[str], dictionary: Set[str]) -> List[str]:
    """
    Находит все возможные слова, которые можно составить из заданного списка букв.
    Каждая буква в списке может использоваться ровно столько раз, сколько она там встречается.
    Возвращает список подходящих слов, отсортированных по длине (по убыванию).
    
    :param letters: Список распознанных букв, например ['a', 'p', 'p', 'l', 'e']
    :param dictionary: Множество допустимых слов словаря.
    :return: Отсортированный список подходящих слов.
    """
    # Переводим буквы в нижний регистр и считаем частоту каждой буквы
    letters = [l.lower() for l in letters if l.isalpha()]
    letter_counts = collections.Counter(letters)
    max_len = len(letters)
    
    valid_words = []
    
    for word in dictionary:
        word_len = len(word)
        # В игре обычно слова состоят как минимум из 3 букв и не могут превышать количество доступных букв
        if word_len < 3 or word_len > max_len:
            continue
            
        # Проверяем, можно ли составить слово из имеющегося набора букв
        word_counts = collections.Counter(word)
        can_make = True
        for char, count in word_counts.items():
            if letter_counts[char] < count:
                can_make = False
                break
                
        if can_make:
            valid_words.append(word)
            
    # Сортируем слова по длине (сначала длинные, затем по алфавиту)
    # Попробуем вводить длинные слова первыми, так как они дают больше очков или открывают больше ячеек
    valid_words.sort(key=lambda w: (len(w), w), reverse=True)
    return valid_words


def can_make_word(word: str, letters: List[str]) -> bool:
    """Проверяет, можно ли составить слово из заданного списка букв."""
    word_counts = collections.Counter(word.lower())
    letter_counts = collections.Counter(l.lower() for l in letters)
    for char, count in word_counts.items():
        if letter_counts[char] < count:
            return False
    return True


def verify_words_match_letters(words: List[str], letters: List[str]) -> bool:
    """
    Проверяет, соответствуют ли слова уровню на экране.
    Допускает незначительные ошибки распознавания OCR (например, пропуск буквы).
    """
    if not words:
        return False
        
    # Уникальные буквы, необходимые для уровня
    level_letters = set()
    for w in words:
        level_letters.update(w.lower())
        
    # Уникальные буквы, распознанные на экране
    screen_letters = set(l.lower() for l in letters if l.isalpha())
    
    # Проверяем, что буквы на экране являются подмножеством букв уровня
    if not screen_letters.issubset(level_letters):
        return False
        
    # Дополнительно проверяем, что пересечение достаточно велико (минимум 3 буквы)
    if len(screen_letters & level_letters) < 3:
        return False
        
    return True


def get_words_for_level(level: int) -> List[str]:
    """Скачивает и парсит страницу конкретного уровня напрямую."""
    if level in _level_cache:
        return _level_cache[level]
    level_url = f"https://wordcityanswers.com/level-{level}.html"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        req = urllib.request.Request(level_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception:
        return []
        
    all_words = set()
    words_block = re.search(r'<div class="words">(.*?)</div>', html, re.DOTALL)
    if words_block:
        block_content = words_block.group(1)
        lines = block_content.split('<br />')
        for line in lines:
            chars = re.findall(r'<span>([A-Za-z])</span>', line)
            if chars:
                word = "".join(chars).lower()
                all_words.add(word)
                
    valid_words = list(all_words)
    valid_words.sort(key=lambda w: (len(w), w), reverse=True)
    _level_cache[level] = valid_words
    return valid_words


def solve_anagrams_web(letters: List[str], level: int = None) -> Tuple[List[str], int]:
    """
    Пытается получить ответы с сайта wordcityanswers.com.
    Если передан level, сначала пробует скачать страницу этого уровня напрямую.
    Если уровень не передан или страница не подошла по буквам, делает поиск по буквам.
    Возвращает кортеж: (список_слов, номер_уровня).
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # 1. Если уровень передан, пробуем получить его напрямую
    if level is not None and level > 0:
        words = get_words_for_level(level)
        if verify_words_match_letters(words, letters):
            return words, level
            
    # 2. Если не совпало или уровень не задан, ищем по буквам
    letters_clean = "".join(sorted("".join(letters).strip().lower()))
    if not letters_clean or not letters_clean.isalpha():
        return [], None

    cache_key = ''.join(sorted(letters_clean))
    if cache_key in _search_cache:
        return _search_cache[cache_key]
        
    search_url = f"https://wordcityanswers.com/?letters={letters_clean}"
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[!] Ошибка подключения к поиску: {e}")
        return [], None
        
    # Проверяем, есть ли на самой странице поиска готовый блок со словами
    # (для нестандартных уровней или когда точного уровня нет в базе, но сайт генерирует анаграммы)
    all_words = set()
    words_block = re.search(r'<div class="words">(.*?)</div>', html, re.DOTALL)
    if words_block:
        block_content = words_block.group(1)
        lines = block_content.split('<br />')
        for line in lines:
            chars = re.findall(r'<span>([A-Za-z])</span>', line)
            if chars:
                word = "".join(chars).lower()
                all_words.add(word)
        if all_words:
            valid_words = list(all_words)
            valid_words.sort(key=lambda w: (len(w), w), reverse=True)
            print(f"[+] Найдены готовые слова непосредственно на странице поиска по буквам ({len(valid_words)} шт.)")
            _search_cache[cache_key] = (valid_words, None)
            return valid_words, None
            
    level_list_match = re.search(r'<ul class="level_list"[^>]*>(.*?)</ul>', html, re.DOTALL)
    if not level_list_match:
        return [], None
        
    # Ищем ссылки и номера уровней
    matches = re.findall(r'href="([^"]+)"[^>]*>Level (\d+)', level_list_match.group(1))
    if not matches:
        return [], None
        
    # Пробуем каждый найденный уровень
    for href, lvl_str in matches:
        lvl = int(lvl_str)
        level_url = urllib.parse.urljoin("https://wordcityanswers.com", href)
        try:
            req_lvl = urllib.request.Request(level_url, headers=headers)
            with urllib.request.urlopen(req_lvl, timeout=3) as response_lvl:
                html_lvl = response_lvl.read().decode('utf-8', errors='ignore')
        except Exception:
            continue
            
        all_words = set()
        words_block = re.search(r'<div class="words">(.*?)</div>', html_lvl, re.DOTALL)
        if words_block:
            block_content = words_block.group(1)
            lines = block_content.split('<br />')
            for line in lines:
                chars = re.findall(r'<span>([A-Za-z])</span>', line)
                if chars:
                    word = "".join(chars).lower()
                    all_words.add(word)
                    
        valid_words = list(all_words)
        valid_words.sort(key=lambda w: (len(w), w), reverse=True)
        
        if verify_words_match_letters(valid_words, letters):
            _search_cache[cache_key] = (valid_words, lvl)
            return valid_words, lvl
            
    return [], None


def get_wheel_letters_from_words(words: List[str]) -> List[str]:
    """
    Вычисляет необходимый набор букв на колесе на основе списка слов уровня.
    Количество каждой буквы на колесе равно максимальному количеству этой буквы в любом одном слове.
    """
    if not words:
        return []
    max_counts = collections.Counter()
    for w in words:
        w_counts = collections.Counter(w.lower())
        for char, count in w_counts.items():
            if max_counts[char] < count:
                max_counts[char] = count
    letters = []
    for char, count in max_counts.items():
        letters.extend([char] * count)
    return sorted(letters)


def get_expected_letter_counts(words: List[str]) -> Dict[str, int]:
    """
    Вычисляет точное количество каждой буквы на колесе.
    Возвращает словарь {буква: количество}.
    """
    if not words:
        return {}
    max_counts: Dict[str, int] = {}
    for w in words:
        w_counts = collections.Counter(w.lower())
        for char, count in w_counts.items():
            if max_counts.get(char, 0) < count:
                max_counts[char] = count
    return max_counts


# Простой тест модуля, если запустить его напрямую
if __name__ == "__main__":
    print("--- Тестирование модуля utils.py ---")
    dict_words = load_dictionary()
    test_letters = ['o', 'w', 'r', 'd', 's']
    print(f"Буквы для теста: {test_letters}")
    solutions = solve_anagrams(test_letters, dict_words)
    print(f"Найдено решений ({len(solutions)} шт.):")
    for s in solutions[:15]:
        print(f"  - {s} (длина {len(s)})")
    if len(solutions) > 15:
        print("  ... и другие")
