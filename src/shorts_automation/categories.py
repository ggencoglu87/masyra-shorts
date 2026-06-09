from __future__ import annotations

CATEGORIES = [
    "Sports",
    "Horror Stories",
    "Funny Kids",
    "Viral News",
    "Gaming",
    "AI",
    "Celebrity",
    "Animals",
    "Movies & TV",
    "Misc Viral",
]

KEYWORDS = {
    "Sports": ["football", "soccer", "basketball", "nba", "nfl", "ufc", "match", "goal", "olympic"],
    "Horror Stories": ["horror", "scary", "ghost", "haunted", "creepy", "mystery", "nightmare"],
    "Funny Kids": ["kid", "kids", "baby", "child", "funny kid", "school prank"],
    "Viral News": ["breaking", "news", "viral", "update", "caught", "shocking", "world"],
    "Gaming": ["game", "gaming", "minecraft", "fortnite", "roblox", "gta", "xbox", "playstation"],
    "AI": ["ai", "openai", "chatgpt", "robot", "artificial intelligence", "model", "automation"],
    "Celebrity": ["celebrity", "actor", "singer", "rapper", "influencer", "taylor", "drake", "movie star"],
    "Animals": ["animal", "dog", "cat", "pet", "wildlife", "rescue", "zoo"],
    "Movies & TV": ["movie", "tv", "netflix", "trailer", "series", "episode", "cinema"],
}


def classify_category(text: str) -> str:
    haystack = text.lower()
    best_category = "Misc Viral"
    best_hits = 0

    for category, keywords in KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in haystack)
        if hits > best_hits:
            best_hits = hits
            best_category = category

    return best_category
